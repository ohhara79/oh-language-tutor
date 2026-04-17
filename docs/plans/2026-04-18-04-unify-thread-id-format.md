# Unify thread-id format across TUI and web

## Context

Thread files live at `state/*/threads/<thread_id>.json`. The two UI modes currently generate different formats:

- **TUI** (`tutor/gui.py:627-628`): `tutor_thread_YYYYMMDDHHMMSS_XXXXXXXX`
- **Web** (`tutor/web.py:166`): `uuid4().hex`

Goal: web adopts the TUI format so filenames sort chronologically and are visually parseable. Factor out a single helper to prevent drift.

Existing `uuid4()`-style files remain loadable (filename is just the stem; `ThreadStore._load_file` keys off `data['thread_id']` internally). No migration needed.

## Change

### `tutor/thread_store.py`
Add a module-level helper:

```python
def new_thread_id() -> str:
    ts = datetime.now(UTC).strftime('%Y%m%d%H%M%S')
    return f'tutor_thread_{ts}_{uuid4().hex[:8]}'
```

Requires adding `from datetime import UTC, datetime` and `from uuid import uuid4`.

### `tutor/web.py`
Replace `thread_id = uuid4().hex` in `/commands/open_thread` with `thread_id = new_thread_id()`. Drop now-unused `uuid4` import.

### `tutor/gui.py`
Replace the inline format in `_open_new_thread` with `tid = new_thread_id()`. Keep `uuid4` import only if still used elsewhere.

## Not changing
- Existing files on disk.
- `TutorEntry.id`, `ThreadMeta.session_id` (unrelated).
- Templates and `app.js` (treat thread_id as opaque string; TUI format is CSS/URL safe).

## Verification
1. `uv run --frozen ruff check tutor/` + `uv run --frozen basedpyright tutor/` — green.
2. `python -c "from tutor.thread_store import new_thread_id; print(new_thread_id())"` — matches `^tutor_thread_\d{14}_[0-9a-f]{8}$`.
3. Web smoke: open a thread, verify new file uses the TUI-style name.
4. TUI smoke: open a thread, verify behavior unchanged.

## Critical files
- `tutor/thread_store.py`
- `tutor/web.py`
- `tutor/gui.py`
