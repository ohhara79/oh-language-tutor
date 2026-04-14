# Thread id format change

## Context

Thread ids are currently generated as `str(uuid4())[:8]` (e.g. `47a34243`), which is opaque. When browsing `state/<lang>/threads/*.json`, there is no way to tell *when* a thread was created or *which anchor line* it belongs to without opening each file. The user wants the id — and therefore the on-disk filename — to carry that information at a glance.

New format:

```
tutor_thread_{YYYYMMDDHHMMSS}_{anchor_idx}_{hash8}
```

Example: `tutor_thread_20260414153012_5_a1b2c3d4`

- `YYYYMMDDHHMMSS`: local creation time (what the user sees on their clock — more recognizable than UTC for "when did I ask this").
- `anchor_idx`: the tutor-entry index the thread is anchored to (already an `int` passed into `_open_new_thread`). No padding — the raw integer.
- `hash8`: 8 hex chars from `uuid4().hex[:8]` to guarantee uniqueness when two threads land on the same anchor in the same second.

Old 8-hex ids are left untouched on disk. The codebase treats `thread_id` as an opaque string everywhere, so mixed-format coexistence works with no extra code.

## Change

Single edit in `tutor/gui.py` at the one generation site.

**File:** `tutor/gui.py`
**Function:** `_open_new_thread` (around line 439)
**Line 443 — replace:**

```python
tid = str(uuid4())[:8]
```

**With:**

```python
ts = datetime.now().strftime('%Y%m%d%H%M%S')
tid = f'tutor_thread_{ts}_{anchor_idx}_{uuid4().hex[:8]}'
```

Add `from datetime import datetime` to the imports at the top of `tutor/gui.py` if not already present. `uuid4` is already imported.

No other code needs to change:

- `tutor/thread_store.py:26` globs `*.json` — accepts any filename, old and new.
- `tutor/thread_store.py:65-66` builds path via `f'{thread_id}.json'` — format-agnostic.
- `tutor/gui.py:409-414` uses `.removeprefix('reopen-' | 'delete-')` — format-agnostic.
- `tutor/types.py` types `thread_id: str` — no constraints.
- `tutor/thread_pool.py` logging — will simply print the new longer id.

## Files touched

- `tutor/gui.py` — 1 line changed + 1 import added.

## Verification

1. `uv run --frozen basedpyright` — confirm no type errors.
2. Launch the GUI (`uv run --frozen tutor ...` or the project's usual entry point), open a tutor session, click **Ask** on a line, and confirm:
   - A new file appears under `state/<lang>/threads/` named `tutor_thread_<14 digits>_<idx>_<8 hex>.json`.
   - The timestamp matches current local time.
   - The anchor index matches the line clicked.
3. Close and reopen the thread via the left-pane list; confirm `Open`/`Del` buttons still work (they use `.removeprefix` so format is irrelevant, but worth a sanity check).
4. Confirm a pre-existing old-format thread (e.g. `47a34243.json`) still loads, displays, and can be deleted — no migration, both formats coexist.
