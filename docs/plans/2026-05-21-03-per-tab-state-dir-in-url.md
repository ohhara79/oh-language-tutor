# Per-tab state-dir via URL path

## Context

The web UI tracks "which state dir is being viewed" with a single domain-wide HTTP cookie `view_state_dir` (set by `POST /commands/open_state_dir`, read by every other route via `_resolve_view_session`). Cookies aren't tab-scoped: when the user opens dir A in one window and dir B in another, the second action overwrites the cookie. Reloading the older tab then reads the other tab's cookie value and loads the wrong dir.

Move the dir choice into the URL path. Each tab's URL is independent, so reload is always correct.

## Approach

URL routes own the dir. The cookie and its helpers are deleted (no compat shim, per project rules). Templates Jinja-interpolate a URL-encoded `view_dir` into every `hx-post`/`hx-get`. JS reads `view_dir` from `body.dataset.stateDir` for the one programmatic `fetch`. `WebSink` carries `view_dir` so SSE-broadcast fragments embed the right URLs.

### Route rewrites (`tutor/web.py`)

| before | after |
|---|---|
| `GET /` (redirects to `/tutor` if cookie set) | `GET /` (always shows picker; no `?picker=1` query branch) |
| `POST /commands/open_state_dir` (sets cookie, redirects to `/tutor`) | `POST /commands/open_state_dir` (redirects to `/tutor/{quote(dir_name)}`; no cookie) |
| `GET /tutor` | `GET /tutor/{dir_name}` |
| `GET /events` | `GET /tutor/{dir_name}/events` |
| `GET /threads/{thread_id}` | `GET /tutor/{dir_name}/threads/{thread_id}` |
| `POST /commands/{open_thread,send_message,hide_thread,delete_thread,delete_tutor_entry,clear_explanation,explain}` | `POST /tutor/{dir_name}/commands/...` |

Delete `VIEW_COOKIE` and `_read_view_cookie`. Change signatures:

- `_resolve_view_session(ctx, dir_name: str) -> DirSession | None` — same traversal defence (`'/' in name`, `'\\' in name`, leading `.`, must match `list_state_dirs(...)` entry).
- `_require_view_session(ctx, dir_name: str) -> DirSession` — raises `404` on miss (path-bound; the old `400` was cookie-bound).

Picker's `current_view` default becomes `ctx.writing_dir.name`.

### `WebSink` carries `view_dir`

`WebSink` is per-`DirSession` and renders `partials/line.html` (and `partials/thread_list.html`) from inside SSE broadcasts that have no request context. Bind `view_dir` at construction.

- `tutor/web_sink.py`: add `view_dir: str` constructor arg; pass it as `view_dir=self._view_dir` into every `env.get_template(...).render(...)` call in this file (`render_line`, `on_thread_list`).
- `tutor/web.py` `make_dir_session`: `WebSink(log=..., tutor_store=..., env=..., view_dir=state_dir.name)`.

### Template changes

`tutor/templates/index.html`:
- Line 11: `<body class="view-list" data-state-dir="{{ view_dir }}" hx-ext="sse" sse-connect="/tutor/{{ view_dir | urlencode }}/events">`
- Line 14: keep `href="/"` (picker is no longer behind `?picker=1`).

`tutor/templates/partials/line.html` lines 9, 19, 39: prefix each `hx-post` URL with `/tutor/{{ view_dir | urlencode }}`.

`tutor/templates/partials/thread_conversation.html` lines 2, 23: same prefix on the two `hx-post` URLs. Pass `view_dir=dir_name` to these renders from `get_thread` and `open_thread` in `web.py`.

`tutor/templates/partials/thread_list.html` line 5 (`hx-get="/threads/{{ t.thread_id }}"`): prefix with `/tutor/{{ view_dir | urlencode }}`. Pass `view_dir` to renders from `index.html` (in scope via parent context), from `WebSink.on_thread_list` (constructor field), and from the `/events` initial-emit (line 405–411 — use `session.state_dir.name`).

`tutor/templates/picker.html`: no change. Form still posts to `/commands/open_state_dir`.

### Static JS changes

`tutor/static/app.js`:
- Line 16: `const datasetName = body.dataset.stateDir || '';`
- Line 203: `fetch('/tutor/' + encodeURIComponent(datasetName) + '/commands/hide_thread', ...)`

`tutor/static/picker.js`:
- Line 35: delete the `document.cookie = 'view_state_dir=; Max-Age=0; path=/'` line.

### Test updates (`tests/test_web.py`)

- Drop `VIEW_COOKIE` import. `_client(...)` no longer takes/seeds a cookie; tests pass `dir_name` into the URL.
- Replace `client.get('/tutor')` → `client.get(f'/tutor/{quote(name, safe="")}')` (and similarly for `/events`, `/threads/...`, `/commands/...`).
- `test_post_open_state_dir_sets_cookie_and_redirects` → assert `Location` equals the URL-encoded `/tutor/<name>`; drop cookie assertion. Rename to `_redirects_to_dir`.
- `test_post_open_state_dir_supports_non_ascii_name`: assert `Location` is the percent-encoded path; `client.get(location)` then succeeds.
- `test_get_tutor_without_cookie_redirects_to_picker` → `test_get_tutor_unknown_dir_redirects_to_picker` hitting `/tutor/nope`.
- `test_get_tutor_with_invalid_cookie_*` → `test_resolve_view_session_rejects_traversal` covering `.hidden`, `a%2Fb` (FastAPI auto-decodes), backslash.
- `test_events_requires_view_cookie` → `test_events_unknown_dir_returns_404` hitting `/tutor/nope/events`.
- `test_get_thread_without_cookie_returns_400` → `test_get_thread_unknown_dir_returns_404`.
- `test_post_clear_explanation_without_cookie_returns_400` → `test_post_clear_explanation_unknown_dir_returns_404`.

## Files to modify

- `tutor/web.py` — route restructure, helper rewrites, drop cookie code.
- `tutor/web_sink.py` — add `view_dir` constructor arg; pass into both template renders.
- `tutor/templates/index.html` — `data-state-dir`, SSE URL.
- `tutor/templates/partials/line.html` — `hx-post` URL prefixes.
- `tutor/templates/partials/thread_conversation.html` — `hx-post` URL prefixes.
- `tutor/templates/partials/thread_list.html` — `hx-get` URL prefix.
- `tutor/static/app.js` — `datasetName` source, `fetch` URL.
- `tutor/static/picker.js` — drop cookie reset.
- `tests/test_web.py` — rewrite cookie-driven tests as path-driven.

## Sharp edges

- `WebSink.render_line` is invoked from broadcasts with no request context, so `view_dir` must be bound at construction, not pulled per call. Correctness follows from subscribers of a session being viewing that session's dir by definition.
- `urlencode` filter output is ASCII; combining with Jinja autoescape can double-escape `&` → `&amp;` in HTML attributes. Browsers decode both, so this is fine — verify with a name containing `&` if such a dir exists.
- FastAPI's `str` path-converter rejects literal `/` segments but accepts `%2F`-decoded slashes. The allowlist check in `_resolve_view_session` (`name in {p.name for p in list_state_dirs(...)}`) still rejects those.
- No backward-compat shim: old `/tutor` bookmarks 404. Intentional — local-dev only.

## Verification

1. `uv run --frozen python -m tutor.web --state-dir <some-dir>` (use whatever launcher this project uses; check `scripts/`).
2. Open two tabs. Tab A → pick dir A. Tab B → pick dir B.
3. Reload tab A — must still show dir A's entries. **This is the bug fix.** Reload tab B — same.
4. In tab A: click "Ask" on a line → opens thread; confirm log writes land in dir A's `tutor.log` (not B's). Same for "Explain", "Delete", thread "Send".
5. DevTools → Network → EventStream on each tab: connections target `/tutor/A/events` and `/tutor/B/events`.
6. `GET /tutor/no-such-dir` → 303 to `/`. `GET /tutor/.hidden` → 303.
7. Non-ASCII: pick a dir like `フレンズ.S01E01.srt`; URL is percent-encoded; reload still works.
8. Picker "Reset settings" still clears `localStorage` cleanly (no cookie line to remove now).
9. `uv run --frozen pytest tests/test_web.py` green.
10. `make lint` green.
