# Fix: Thread list UI doesn't update after delete button is clicked

## Context

In the Textual TUI (`tutor/gui.py`), clicking the **Del** button on a `ThreadListItem` queues a `DeleteThreadCmd` but the thread list in the UI still shows the just-deleted thread until the user does something else that triggers a refresh.

### Root cause (race condition)

`OhLanguageTutorApp.on_button_pressed` handles the delete button at `tutor/gui.py:415-418`:

```python
elif btn_id.startswith('delete-'):
    tid = btn_id.removeprefix('delete-')
    self._cmd_queue.put_nowait(DeleteThreadCmd(thread_id=tid))
    self._refresh_thread_list()
```

The flow is:

1. `DeleteThreadCmd` is **put on an asyncio queue** (fire-and-forget) — `_cmd_queue.put_nowait(...)`.
2. `_refresh_thread_list()` runs **immediately** on the same event loop turn and calls `self._pool.list_threads()` → reads JSON files from disk.
3. The `_dispatch_commands` coroutine in `tutor/core.py:154-175` only consumes the command on a later tick, which calls `pool.delete_thread(...)` → `store.delete_thread(...)` → `p.unlink(...)` (`tutor/thread_store.py:59-62`).

So `_refresh_thread_list()` re-reads disk *before* the file is unlinked, and the UI re-mounts the deleted thread. No subsequent refresh is wired up, so the stale row stays on screen.

## Fix

Emit the updated thread list from the pool **after** deletion completes, via the existing `OutputSink.on_thread_list` hook (`tutor/types.py:81-83`). The GUI's `on_thread_list` handler (`tutor/gui.py:393-394`) already calls `_refresh_thread_list()`, so the UI will refresh automatically. Remove the racy synchronous refresh from the button handler.

This matches the existing pattern where `FollowupThreadPool` emits events through `self._sink` (e.g. `on_thread_chunk`, `on_thread_done` at `tutor/thread_pool.py:210,220,227`).

### Changes

1. **`tutor/thread_pool.py`** — in `delete_thread` (around line 168-171), after `self._store.delete_thread(thread_id)`, emit:
   ```python
   self._sink.on_thread_list(self.list_threads())
   ```

2. **`tutor/gui.py`** — in `on_button_pressed` (line 415-418), drop the immediate `self._refresh_thread_list()` call. The sink callback will trigger it once the delete has actually happened:
   ```python
   elif btn_id.startswith('delete-'):
       tid = btn_id.removeprefix('delete-')
       self._cmd_queue.put_nowait(DeleteThreadCmd(thread_id=tid))
   ```

No changes needed to `TerminalSink.on_thread_list` — it is already a no-op.

## Critical files

- `tutor/thread_pool.py:168-171` — add sink emission after delete
- `tutor/gui.py:415-418` — remove racy refresh call
- `tutor/gui.py:393-394` — already correct (handler that refreshes on `on_thread_list`)
- `tutor/types.py:81-83` — `OutputSink.on_thread_list` protocol (no changes)
- `tutor/sink.py:55-56` — `TerminalSink.on_thread_list` (no changes, already a no-op)

## Verification

1. Run the TUI (check `Makefile` / `scripts/bladerunner.sh` for the launcher).
2. Create a followup thread by clicking **Ask** on a line, send a message so the thread is persisted.
3. Hide the thread (Escape) to return to the list; confirm the thread appears in the right-pane list.
4. Click **Del** on that row.
5. **Expected:** the row disappears from the list immediately (within a single event loop tick after the dispatcher processes the command — sub-100ms, visually instant).
6. Confirm the JSON file is gone from the state dir.
7. Also verify no regression for the **Open** / **Ask** / **Esc hide** flows — the thread list should still refresh correctly in those cases (`on_mount` and `action_hide_thread` still call `_refresh_thread_list()` directly, which is fine because they don't depend on an async queue).

## Lint / typecheck

Run the project's checks after editing (`uv run --frozen ...` per the project convention).
