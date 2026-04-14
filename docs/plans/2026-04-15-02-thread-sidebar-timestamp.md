# Show full local timestamp in thread sidebar and HTML export

## Context

The thread sidebar currently shows only the date portion of each thread's creation time (e.g. `2026-04-14`), produced by a naive `created_at[:10]` slice on an ISO-8601 UTC string. The user wants the full timestamp down to the second, in local time, formatted as `YYYY-MM-DD HH:MM:SS` (e.g. `2026-04-14 15:45:12`). The HTML export uses the same `[:10]` slice and should change in lockstep so both UIs stay consistent.

Stored format (from `tutor/thread_pool.py:105`):
```
datetime.datetime.now(tz=datetime.UTC).isoformat()
# e.g. "2026-04-14T15:45:12.123456+00:00"
```

## Changes

### 1. Add a small formatter helper

Add one module-level function to `tutor/types.py` (next to the `ThreadMeta` dataclass — the type it serves):

```python
def format_created_at_local(created_at: str) -> str:
    """Convert a stored ISO-8601 UTC timestamp to local 'YYYY-MM-DD HH:MM:SS'."""
    return (
        datetime.datetime.fromisoformat(created_at)
        .astimezone()
        .strftime('%Y-%m-%d %H:%M:%S')
    )
```

`.astimezone()` with no argument converts an aware datetime to the system's local timezone. `fromisoformat` handles the `+00:00` suffix since Python 3.11.

Add `import datetime` to `tutor/types.py` if not already present.

### 2. Use it in the thread sidebar

File: `tutor/gui.py:185`

Replace:
```python
f'{anchor_short}  ({msgs} msgs, {self._meta.created_at[:10]})',
```
with:
```python
f'{anchor_short}  ({msgs} msgs, {format_created_at_local(self._meta.created_at)})',
```

Add `format_created_at_local` to the existing `from tutor.types import ...` line.

### 3. Use it in the HTML export

File: `tutor/html_export.py:103`

Replace:
```python
date = html.escape(thread.created_at[:10])
```
with:
```python
date = html.escape(format_created_at_local(thread.created_at))
```

Rename the local variable if desired (e.g. `timestamp`) — optional cleanup; check downstream usage in the same file first and only rename if it doesn't ripple.

Add the import to `tutor/html_export.py`.

## Critical files

- `tutor/types.py` — add helper
- `tutor/gui.py` — sidebar render (line 185 in `ThreadListItem.compose`)
- `tutor/html_export.py` — HTML export (line 103)

## Notes / considerations

- The sidebar label width is `1fr` (CSS at `tutor/gui.py:225`); the new string adds 9 chars (`" HH:MM:SS"`) so Textual may wrap it to an extra line for long anchors. This matches the existing wrap behavior and is acceptable unless the user wants single-line truncation — out of scope here.
- Existing threads on disk already store full ISO-8601 timestamps, so no migration is needed.
- `anchor_short[:60]` truncation is unchanged.

## Verification

1. Type-check: `uv run --frozen basedpyright`
2. Run the app: `uv run --frozen python -m tutor` (or the project's usual entrypoint) and visually confirm the thread sidebar shows e.g. `(2 msgs, 2026-04-14 15:45:12)` in local time.
3. Export a session to HTML (existing export flow) and confirm the rendered timestamp matches.
4. Sanity-check timezone conversion: open a thread created at a known UTC instant and confirm the displayed local time matches the expected offset.
