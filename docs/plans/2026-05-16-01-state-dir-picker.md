# Tutor-data picker page + decoupled write vs. view state dirs

## Context

Today, `--state-dir` plays two roles at once: it is **where stdin-piped raw
text gets written**, and it is also **the only directory the UI ever shows**.
A user who just wants to revisit a previous session has to remember/type the
right `--state-dir` on the CLI even though they're not streaming any new text.
There is no way from inside the app to switch which tutor-data directory
you're looking at.

This change splits the two roles:

- `--state-dir` keeps its meaning, but **only as the write target** — where
  any new stdin lines are persisted.
- Which directory the **UI displays** becomes a runtime choice via a new
  picker page that is shown on launch.
- The two can be the same (common case: live streaming with the UI watching
  that same dir) or different (browse-old-data case: stdin is being written
  into `state/srt` but the user is looking at `state/bladerunner.org`).

Intended outcome: launching without piping stdin gracefully lands on a picker
instead of silently dumping the user into an empty or wrong dataset.

## Design choices

- **Discovery scope** — picker lists subdirectories of
  `Path(--state-dir).parent`. No registry file, no `--data-root` flag.
- **Routing** — picker (`GET /`) is the landing page in every case.
  `--state-dir` is the pre-selected default *and* the write target.
- **Permissions on picked dir** — full read/write: browse lines, open and
  continue threads, request explanations. The only thing that *doesn't*
  happen on a non-writing picked dir is new stdin text appearing.
- **stdin vs pick** — stdin lines always go to `--state-dir` regardless of
  what the user picked to view. Write and view are independent.
- **New-dir creation** — not in this change; CLI-only.

## Architecture

### Per-dir session bundle

Each tutor-data directory needs its own bundle of state:
`TutorStore` + `ThreadStore` + `WebSink` + `FollowupThreadPool` + open
`tutor.log` handle. Introduce a `DirSession` dataclass holding these. A
single cache `dict[Path, DirSession]` in `WebContext` lazily materializes one
per dir when first selected.

### Writing dir

At startup, eagerly create the `DirSession` for `--state-dir` and wire
`stdin_loop` to **that** session's sink. The sink never moves.

### Viewing dir

Track the currently selected viewing dir in a **cookie**
(`view_state_dir`, value = dir basename). All existing routes read the cookie,
look up the `DirSession`, and operate on it. No URL path changes. If the
cookie is missing/invalid, `GET /tutor` redirects to `GET /`.

### Routes

| Route | Behavior |
|---|---|
| `GET /` | Picker. Lists subdirs of `Path(--state-dir).parent`. Pre-selects `--state-dir`'s basename. Marks the writing dir. |
| `POST /commands/open_state_dir` | Form post with chosen dir name. Validates. Sets cookie. Redirects to `/tutor`. |
| `GET /tutor` | The current `/` index implementation, but resolves to cookie-selected `DirSession`. |
| All other existing routes | Same as today, but use the cookie-resolved `DirSession`. |

### SSE isolation

Each `DirSession` has its own `WebSink` with its own subscriber set. Stdin
events push to the writing dir's sink only — browser tabs viewing a different
dir simply don't see them. No event filtering needed; physical sink
separation does the job.

## Files to change

- `tutor/web.py` — main change: introduce `DirSession`, refactor
  `WebContext`, add picker + `/tutor` routes, swap store/sink/pool lookups
  to cookie-resolved session, expand shutdown to flush all cached sessions.
- `tutor/args.py` — clarify `--state-dir` help text as the write target.
- `tutor/templates/picker.html` — new template.
- `tutor/templates/index.html` — add "Switch dataset" header link +
  viewed-dir indicator.
- `tutor/static/app.css` — minimal picker styles.
- `tests/test_web.py` — update for new `WebContext` shape; add tests for
  discovery, picker route, cookie routing, two-dir isolation.

`TutorStore`, `ThreadStore`, `WebSink`, `FollowupThreadPool` are reused
verbatim — they already work per-directory.

## Open questions to settle during implementation

1. **Log file handles** — if the user opens many dirs in one session, we
   keep all `tutor.log` files open. Acceptable for normal use (handful of
   dirs); revisit if scaling.
2. **Discovery filter rules** — show all direct subdirs of the parent.
   Hidden dirs (leading `.`) and non-dir entries are skipped.

## Verification

End-to-end (manual):

1. `uv run --frozen main.py` (no stdin)
   - Picker at `/`. Subdirs of `state/` listed; `state` (the default
     `--state-dir`) marked as "writes here".
   - Pick `bladerunner.org` → `/tutor` shows its old lines and threads.
   - Open a thread on a line, send a follow-up → response appears,
     persisted under `state/bladerunner.org/threads/`.
   - "Switch dataset" link → back at picker. Pick `srt.org` → its content
     renders.
2. `cat some.srt | uv run --frozen main.py --state-dir state/srt`
   - Picker shown with `srt` pre-selected. Pick `srt` → see new lines.
   - "Switch dataset" → pick `bladerunner` → see its content, no incoming
     `srt` lines. `state/srt/tutor.json` still grows on disk.
3. Bad cookie value → `/tutor` redirects to `/`.

Automated: `make lint` clean; updated and new tests green.
