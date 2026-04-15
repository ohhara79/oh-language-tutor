# Plan: Delete button in left pane + stable anchor IDs

## Context

The left pane currently shows each explained line with an **Ask** button. The user
wants to add a **Delete** button next to it so stale or unwanted lines can be
removed from `state/bladerunner/tutor.json`.

The blocker is the existing `anchor_idx` system: a thread's link back to the
left pane is the *positional index* of the entry in `tutor.json`
(`tutor/types.py:54`, `tutor/thread_store.py:42,77`, `tutor/thread_pool.py:87-94`,
`tutor/gui.py:417,440-447,488,522`, `tutor/html_export.py:148-172`). Removing
an entry at position *N* silently shifts every later entry, so every thread
with `anchor_idx ≥ N` would start pointing at the wrong anchor — both for the
right-pane scroll target *and* for the 100-line context window passed to
Claude. Shifting thread metadata in lockstep on delete is possible but fragile,
and it couples storage layout to UI actions forever.

The clean fix is to give each tutor entry a **stable unique ID**, make threads
reference that ID, and derive the positional index on demand when building the
context window. Delete then just removes an entry and cascades to its threads;
unrelated threads keep working regardless of how positions shifted.

Design decisions confirmed with the user:
- **Cascade delete**: removing a tutor entry also deletes every thread whose
  `anchor_id` matches it.
- **Two-click confirm**: first click arms the button (label flips to
  `Confirm?`), a short timer disarms it, a second click within the window
  performs the delete. No modal.

## Approach

Introduce a stable `id: str` on `TutorEntry` (UUID hex, generated at creation
time). Persist it in `tutor.json`. Replace `anchor_idx` with `anchor_id` in
`ThreadMeta` and `OpenThreadCmd`. At open/reopen time, resolve `anchor_id` to
the current position in the tutor list to build the context window and to
scroll the left pane. Migrate existing state at startup.

## Data model changes

`tutor/types.py`
- `TutorEntry` gains `id: str` (default `field(default_factory=lambda: uuid4().hex)`).
- `ThreadMeta`: replace `anchor_idx: int = -1` with `anchor_id: str = ''`.
  Keep reading legacy `anchor_idx` only in `ThreadStore._load_file` for the
  one-shot migration; stop writing it.
- `OpenThreadCmd.anchor_idx: int` → `OpenThreadCmd.anchor_id: str`.
- New command: `DeleteTutorEntryCmd(anchor_id: str)`.
- `OutputSink` gains `on_tutor_entry_removed(anchor_id: str) -> None`.

## Storage changes

`tutor/tutor_store.py`
- Serialize `{"id": ..., "raw": ..., "explanation": ...}`.
- `load()` returns entries; a legacy entry without `"id"` is materialised with
  a fresh UUID so downstream code is uniform.
- New `migrate()` method: loads, and if any entry lacked an id on disk,
  rewrites the file once. Call from `run_gui` and `run_terminal` before the
  app starts.
- New `delete(anchor_id: str) -> bool`: atomic rewrite without the matching
  entry. Returns False if id not found (no-op).
- New `index_of(anchor_id: str) -> int | None` helper (used by `thread_pool`
  and `gui`).
- Keep the hot-path `load()` pure (no side-effects) so `open_thread` can keep
  calling it.

`tutor/thread_store.py`
- Write `"anchor_id"` only; stop writing `"anchor_idx"`.
- Read path accepts either:
  - `anchor_id` present → use it.
  - Only `anchor_idx >= 0` present → flagged for migration.
- New `migrate(tutor_entries: list[TutorEntry]) -> None`: for every file with
  no `anchor_id` but `anchor_idx >= 0 < len(entries)`, set
  `anchor_id = entries[anchor_idx].id` and rewrite. Files with
  `anchor_idx == -1` or out of range keep `anchor_id=''` (orphans — they
  already render via `anchor_raw`, just can't scroll back).
- New `delete_by_anchor_id(anchor_id: str) -> list[str]`: returns ids of
  deleted threads so the pool can close any active ones.

## Thread pool changes

`tutor/thread_pool.py`
- `open_thread(thread_id, anchor_id)`:
  - Load tutor entries, find index by id; error if missing.
  - Use that index to slice the context window exactly as today
    (`entries[max(0, idx-100):idx]`).
  - Store `anchor_id` on `ThreadMeta`.
- New `delete_tutor_entry(anchor_id: str) -> None`:
  1. Find every active thread with `meta.anchor_id == anchor_id`;
     `await self.hide_thread(tid)` on each to flush in-flight streams.
  2. `deleted = self._store.delete_by_anchor_id(anchor_id)` — removes files.
  3. `self._tutor_store.delete(anchor_id)` — rewrites `tutor.json`.
  4. `self._sink.on_thread_list(self.list_threads())` + new
     `self._sink.on_tutor_entry_removed(anchor_id)`.

## GUI changes

`tutor/gui.py`
- `LineBlock(raw, tutor_id)` replaces `LineBlock(raw, tutor_pos)`; buttons
  become `ask-{tutor_id}` and `line-delete-{tutor_id}` (distinct prefix so it
  does not collide with the existing thread `delete-{thread_id}`).
- `on_explanation`: generate `entry = TutorEntry(raw=raw, explanation=text)`
  (id auto-generated), mount `LineBlock(raw, entry.id)`, then
  `tutor_store.append(entry)`.
- `_restore_tutor_entries`: pass `entry.id` to `LineBlock`.
- `on_button_pressed`:
  - `ask-<id>` → `_open_new_thread(anchor_id=id)`.
  - `line-delete-<id>` → two-click confirm state machine:
    - First press: record `self._delete_arming_id = id`, set button label to
      `Confirm?`, add `.armed` CSS class, schedule
      `self.set_timer(3.0, self._disarm_delete)`.
    - Pressing a *different* line-delete disarms the previous and arms the new
      one.
    - Second press on the armed id: enqueue
      `DeleteTutorEntryCmd(anchor_id=id)`, clear arm state.
- `_scroll_left_pane_to_anchor(anchor_idx)` → `_scroll_left_pane_to_anchor_id(anchor_id)`:
  match LineBlocks by `tutor_id` attribute; no-op on empty string.
- `_open_new_thread(anchor_id)`: build `OpenThreadCmd` with `anchor_id`;
  resolve current position from tutor_store only for the `Thread opened for:`
  label.
- Add `OutputSink.on_tutor_entry_removed(anchor_id)` handler:
  find the LineBlock with matching `tutor_id`, remove it plus the sibling
  ExplanationBlock (the pair that was mounted together in `on_explanation`),
  decrement `self._tutor_count`. Also clear `self._delete_arming_id` if equal.

Dispatcher (`_dispatch_commands`) adds a `DeleteTutorEntryCmd` case that
calls `pool.delete_tutor_entry(cmd.anchor_id)`.

## HTML export

`tutor/html_export.py`
- Replace `threads_by_pos: dict[int, ...]` with
  `threads_by_id: dict[str, ...]` keyed on `anchor_id`.
- Iterate tutor entries by position as today; look up
  `threads_by_id.get(entry.id, [])`.
- Orphans: threads with empty `anchor_id` or an `anchor_id` no longer in the
  tutor list.

## Migration

`run_gui` / `run_terminal` (in `tutor/core.py` and/or entry points) call, in
order, before constructing the pool:
```python
tutor_store.migrate()
thread_store.migrate(tutor_store.load())
```
Both are idempotent: next startup is a cheap no-op if nothing needs fixing.

## CSS

Add a `.line-delete-btn` rule (narrow, red variant) and an `.armed` class that
flips its background so the two-click confirm state is visually obvious.

## Files to modify

- `tutor/types.py` — dataclass updates, new command, new sink method.
- `tutor/tutor_store.py` — persist id, `delete`, `index_of`, `migrate`.
- `tutor/thread_store.py` — persist `anchor_id`, `delete_by_anchor_id`,
  `migrate`.
- `tutor/thread_pool.py` — open by id, `delete_tutor_entry`.
- `tutor/gui.py` — LineBlock wiring, two-click confirm, sink handler,
  dispatcher case, scroll-by-id.
- `tutor/html_export.py` — index by id.
- `tutor/core.py` — wire migrations at startup; `OpenThreadCmd` field rename
  at call sites.

## Verification

1. `uv run --frozen basedpyright` clean.
2. Pre-migration fixture: copy an existing `state/bladerunner/tutor.json`
   and `state/bladerunner/threads/*.json` to a scratch dir, point the app at
   it, launch:
   - Confirm tutor entries render with their prior content.
   - Confirm every non-legacy thread (those with `anchor_idx >= 0`) still
     scrolls the left pane to the correct line and still opens/replies.
   - Confirm legacy threads (`anchor_idx == -1`) still appear in the sidebar.
3. Post-migration: inspect `tutor.json` — each entry now has a UUID `id`;
   inspect a migrated thread file — has `anchor_id`, no longer writes
   `anchor_idx`.
4. Fresh pipe run: `tail -f somefile | uv run --frozen oh-language-tutor gui`
   — ask, reply, delete line, reask on neighbouring lines; confirm the
   deleted LineBlock disappears and its threads are gone from the sidebar.
5. Two-click UX: first click of Delete flips label to `Confirm?`; waiting
   3s+ reverts; clicking a *different* delete disarms the first; second
   click within the window deletes.
6. HTML export (`Ctrl+E`) still renders all surviving threads under their
   correct anchor and lists orphans separately.
