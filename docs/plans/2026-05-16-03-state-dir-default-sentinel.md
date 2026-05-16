# Sentinel default `--state-dir` so the picker discovers the right parent

## Context

`tutor/args.py` defines `DEFAULT_STATE_DIR = PROJECT_DIR / 'state'`.
When the user launches `oh-language-tutor` without `--state-dir`, that
default flows into `run_web` (`tutor/web.py`):

```python
writing_dir = Path(args.state_dir).expanduser().resolve()  # → <project>/state
discovery_parent = writing_dir.parent                       # → <project>
```

So `list_state_dirs(<project>)` returns `docs/`, `extras/`, `scripts/`,
`tests/`, `tutor/`, `state/`, etc. — the picker shows project source
directories instead of the user's tutor-data directories under
`state/`. The bug is fully a defaults issue; once the user passes any
real `--state-dir` like `state/srt`, the parent resolves correctly.

Intended outcome: launching with no flags lands the picker on the
correct discovery parent (the existing `state/` directory) and the
sentinel writing dir doesn't conflict with any real dataset name.

## Design

Single-line fix:

```python
DEFAULT_STATE_DIR = PROJECT_DIR / 'state' / 'scratch'
```

That makes the default write target a sentinel directory inside
`state/`, so:

- `discovery_parent = state/`.
- `list_state_dirs(state/)` returns the real tutor-data dirs
  (`srt/`, `bladerunner/`, `bladerunner.org/`, etc.) plus `scratch`.
- The picker pre-selects `scratch` (the writing dir) with the
  "writes here" badge. The user can pick any sibling to view; if they
  don't pipe stdin, `scratch/` stays empty on disk — the lazy-log
  change from the prior commit keeps `tutor.log`/`threads/` from
  landing there.

Naming: `scratch` reads as "scratch space" for unattributed writes,
sorts alphabetically with the other dirs, and matches typical *nix
conventions for transient working dirs.

### Why nothing else needs to change

- `make_dir_session` already calls `state_dir.mkdir(parents=True,
  exist_ok=True)`: first launch creates an empty `state/scratch/`.
- The picker template already pre-selects the current view dir,
  falling back to the writing dir's name — which now resolves to
  `scratch`, a valid entry in the list.

## Files to change

- `tutor/args.py` — change `DEFAULT_STATE_DIR`.
- `README.md` — `--state-dir` row in the flag table: default
  `state/scratch`, description updated to match the post-picker
  meaning ("write target for stdin lines").
- `tests/test_args.py` — add an assertion in
  `test_no_args_produces_namespace_with_defaults` that the default
  resolves to `state/scratch`, so a future rename can't silently drift
  back to a broken default.

No code in `tutor/web.py`, templates, CSS, or other tests needs to
change.

## Verification

End-to-end (manual):

1. `rm -rf state/scratch` (clean slate).
2. `uv run --frozen main.py` (no `--state-dir`).
3. Open the picker at `/`. Confirm the list shows only the existing
   tutor-data dirs under `state/` (`srt`, `bladerunner`, …) plus the
   just-created `scratch`. **No** project-root entries like `docs/`,
   `tutor/`, `tests/` appear.
4. Confirm `scratch` is pre-selected with the "writes here" badge.
5. Pick a real dir, browse `/tutor`, quit. `state/scratch/` is still
   an empty directory on disk (no `tutor.log`, no `threads/`).

Automated: `make lint` clean; the added args-test assertion passes
together with the rest of the suite.
