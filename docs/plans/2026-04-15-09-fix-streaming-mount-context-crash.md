# Fix residual double-click-delete shutdown crash

## Context

Commit `c0dc9e1` ("Fix two click delete crash", plan
`docs/plans/2026-04-15-08-fix-two-click-delete-crash.md`) partially fixed a
crash that occurred when the user clicked the left-pane "DEL" button twice.
That fix:

1. Marshalled `on_thread_list` and `on_tutor_entry_removed` through
   `self.call_later(...)` so widget removal runs in the app task's context
   (where Textual's `active_app` ContextVar is set).
2. Tracked the 3-second arming timers (`_delete_arming_timer`,
   `_thread_delete_arming_timer`) so `_disarm_delete()` actively stops them.

The user now reports the same crash still reproduces when they double-click
left-pane "DEL" **while a new message is streaming in**. The traceback
terminates in `textual/timer.py:120 await timer._task` with
`LookupError: <ContextVar name='active_app'>` during `_message_loop_exit`
→ `Timer._stop_all` on app shutdown.

### Root cause (why c0dc9e1 is insufficient)

`stdin_task` and `dispatch_task` are created with `asyncio.create_task(...)`
at `tutor/gui.py:791-792` — **before** `await app.run_async()` at line 795.
They inherit a `contextvars.Context` that does **not** contain Textual's
`active_app`. The dispatcher also spawns `_stream_response` tasks inside the
pool (`tutor/thread_pool.py:277`) that inherit the same broken context.

The sink callbacks invoked from those tasks currently mutate widgets
directly:

- `on_raw_line` (`gui.py:374`) — removes placeholder.
- `on_explanation` (`gui.py:381`) — mounts `LineBlock` + `ExplanationBlock`.
- `on_thread_chunk` (`gui.py:396`) — mounts `Static`, calls `.update()`,
  `.scroll_end()`.
- `on_thread_done` (`gui.py:407`) — `.update()`, `inp.focus()`.
- `on_error` (`gui.py:446`) — `.update()`.

When Textual's widget machinery schedules timers/tasks as a side effect of
those mutations, the new `_task` inherits the calling context — which lacks
`active_app`. Any later `self.app` access inside those tasks raises
`LookupError`. The exception surfaces at shutdown when `Timer._stop_all`
awaits the leftover task.

Double-clicking "DEL" while streaming is the repro because it interleaves
`on_thread_chunk` (bad-context mount) with the widget-removal path,
increasing the chance of a stray timer being alive at shutdown.

## Approach

Mirror the `on_thread_list` / `on_tutor_entry_removed` pattern for every
remaining sink callback. Split each into a thin method that only calls
`self.call_later(...)` and a `_apply_*` helper that does the actual widget
mutation in the app task's context.

This keeps the callback fire-and-forget for the dispatcher/stdin tasks,
preserves FIFO ordering (the app message pump flushes `call_later`
callbacks in order), and matches the pattern already accepted in the
codebase.

## Changes

All changes in `tutor/gui.py`, inside `OhLanguageTutorApp`:

1. `on_raw_line` (line 374) — keep the `self._session_log.write(...)` side
   effect inline (non-widget I/O; safe from any task). Marshal the widget
   mutation: `self.call_later(self._apply_raw_line)`. Move the
   `#stream-placeholder` removal into `_apply_raw_line`.

2. `on_explanation` (line 381) — keep the log writes and
   `self._tutor_store.append(entry)` inline (non-widget side effects).
   Build `entry = TutorEntry(raw=raw, explanation=text)` once so the
   `entry.id` used by `tutor_store.append` matches the `LineBlock` id.
   Marshal the widget mutations:
   `self.call_later(self._apply_explanation, raw, text, entry.id)`.

3. `on_thread_chunk` (line 396) —
   `self.call_later(self._apply_thread_chunk, thread_id, chunk)`; move
   body verbatim into `_apply_thread_chunk`.

4. `on_thread_done` (line 407) —
   `self.call_later(self._apply_thread_done, thread_id)`; move body
   verbatim into `_apply_thread_done`.

5. `on_error` (line 446) — keep the pre-mount
   `self._pending_errors.append(msg)` branch inline (runs before the
   screen stack exists; does not touch widgets). Marshal the
   status-bar update: `self.call_later(self._apply_error, msg)`.

## Files touched

- `tutor/gui.py` — five methods refactored as above; no new imports, no
  behavioural change beyond context-marshalling.

## Verification

1. `uv run --frozen basedpyright tutor/gui.py` — type check passes.
2. `uv run --frozen pytest` — existing tests pass.
3. Manual repro of the original bug:
   - Launch the app with a dialog pipe that streams new lines (e.g. via
     `scripts/bladerunner.sh`).
   - While a new explanation is streaming into the left pane, click "DEL"
     on an existing entry to arm it, then click "DEL" again to confirm.
   - Repeat several times, then quit the app (Ctrl-C / `q`).
   - Expect: clean exit, no `LookupError: active_app` in the traceback.
4. Sanity check that streaming output still renders: open a thread, send
   a message, confirm chunks appear and the final markdown re-renders on
   completion.
