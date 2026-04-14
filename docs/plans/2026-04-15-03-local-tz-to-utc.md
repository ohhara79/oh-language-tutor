# Switch local-timezone usage to UTC

## Context

Thread timestamps are stored as UTC ISO-8601 strings in `ThreadMeta.created_at` (see `tutor/thread_pool.py:105`), but two sites currently convert to / use the machine's local timezone:

1. `tutor/types.py:58-64` — `format_created_at_local()` renders the stored UTC timestamp in local tz for display in the thread sidebar and HTML export.
2. `tutor/gui.py:453` — `datetime.now().strftime(...)` embeds local-time digits into newly-generated thread IDs.

Two other sites already handle UTC correctly and do not need to change:
- `tutor/thread_pool.py:105` stores `datetime.now(tz=datetime.UTC).isoformat()` ✓
- `tutor/html_export.py:176` renders the footer with `datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')` ✓

Goal: make every user-visible timestamp and every generated thread ID reflect UTC, so behavior is consistent regardless of the machine's local tz and matches the storage layer.

## Changes

### 1. `tutor/types.py` — rename and re-aim the formatter

Replace `format_created_at_local` with a UTC version. Rename because the old name now lies about its behavior.

```python
def format_created_at_utc(created_at: str) -> str:
    """Format a stored ISO-8601 UTC timestamp as 'YYYY-MM-DD HH:MM:SS UTC'."""
    return (
        datetime.datetime.fromisoformat(created_at)
        .astimezone(datetime.UTC)
        .strftime('%Y-%m-%d %H:%M:%S UTC')
    )
```

Notes:
- `.astimezone(datetime.UTC)` handles both aware-UTC and (hypothetical) aware-non-UTC inputs correctly; stored values are already UTC so this is effectively a no-op but makes intent explicit.
- Append ` UTC` to the rendered string for the same reason `html_export.py:176` already does — users should see that the time isn't local.

### 2. `tutor/gui.py`

- Line 41: import `format_created_at_utc` instead of `format_created_at_local`.
- Line 186: call the renamed function.
- Line 453: change

  ```python
  ts = datetime.now().strftime('%Y%m%d%H%M%S')
  ```

  to

  ```python
  ts = datetime.now(UTC).strftime('%Y%m%d%H%M%S')
  ```

  and update the `from datetime import datetime` line at the top (line 10) to `from datetime import UTC, datetime`.

### 3. `tutor/html_export.py`

- Line 15: import `format_created_at_utc` instead of `format_created_at_local`.
- Line 104: call the renamed function.

## Critical files

- `tutor/types.py` (rename + rewrite the formatter)
- `tutor/gui.py` (import, call site line 186, thread-ID timestamp line 453, import line 10)
- `tutor/html_export.py` (import line 15, call site line 104)

## Verification

- Type-check: `uv run --frozen basedpyright`.
- Run tests if any: `uv run --frozen pytest` (skip silently if no tests touch these paths).
- Manual smoke: launch the GUI, open an existing thread with a known `created_at`, confirm the sidebar shows the UTC wall-clock time with a trailing ` UTC`. Open a new thread and confirm the generated ID's `YYYYMMDDHHMMSS` segment matches UTC.
- Export a thread to HTML and confirm the thread header timestamp also reads as UTC.
