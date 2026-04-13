# Make LineRegistry capacity unlimited

## Context
The left pane GUI displays all lines without any limit, but the internal
`LineRegistry` silently evicts entries after 500 lines. This mismatch means
users can see and click Ask buttons on old lines that the registry has already
dropped, resulting in a silent "line not found" failure. Since each
`LineRecord` is tiny (an int, a string, and an optional string), there is no
practical reason to cap the registry.

## Changes

**File: `tutor/registry.py`**

1. Remove the `max_size` parameter from `__init__` and use an unbounded
   `deque()` (no `maxlen`).
2. Remove the `_max_size` field.
3. Remove the `_trim_index` method — nothing gets evicted so trimming is
   unnecessary.
4. Remove the `self._trim_index()` call in `add_line`.

## Verification
- Run `uv run --frozen python -m pytest` (if tests exist).
- Launch the app, scroll past 500 lines, and confirm Ask buttons still work on
  early lines.
