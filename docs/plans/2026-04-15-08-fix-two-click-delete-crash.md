# Fix app crash on two-click left-pane delete

## Context

Clicking the left-pane "Del" button twice (i.e. confirming a line delete)
causes the app to exit with:

```
LookupError: <ContextVar name='active_app' at 0x...>
```

The traceback bottoms out in `textual/timer.py:120 stop_timer` → `await
timer._task`. That means a Timer task raised `LookupError: active_app`
while the app was tearing down. The user did **not** try to quit —
something in the second click is forcing shutdown.

### Two bugs collide on the second click

**Bug A — Sink callbacks mutate widgets from the dispatcher task.**
The dispatcher task is created at `tutor/gui.py:777` **before**
`await app.run_async()` runs at `tutor/gui.py:780`, so the dispatcher
task's `contextvars.Context` never has Textual's `active_app`
`ContextVar` set. When the second click enqueues `DeleteTutorEntryCmd`,
the dispatcher runs `pool.delete_tutor_entry(...)`
(`tutor/thread_pool.py:211-221`), which calls back into the app's sink:

- `self._sink.on_thread_list(...)` → `_refresh_thread_list()`
  (`tutor/gui.py:660-672`) — this uses the **app's own**
  `self.query_one(...)` and `container.mount(...)`. `App.app` returns
  `self`, so it's mostly fine.
- `self._sink.on_tutor_entry_removed(anchor_id)`
  (`tutor/gui.py:419-439`) — this calls `block.remove()` on a
  **descendant** widget. `Widget.app` reads `active_app.get()` and
  raises `LookupError` when it's unset in the current task context.

That error kills the dispatcher task. On top of that, half-finished
`AwaitRemove` / `AwaitMount` objects get scheduled into Textual's
callback pump anyway, which is what surfaces later during shutdown.

**Bug B — The 3-second disarm timer handle is discarded.**
`tutor/gui.py:485` and `tutor/gui.py:511` schedule a disarm timer via
`self.set_timer(3.0, ...)` but throw the returned `Timer` away. When
the user confirms (second click), the timer is *still pending*. Once
the widget tree starts tearing down (from Bug A's fallout, or when the
app later exits for any reason), Textual walks the descendants and
calls `_stop_all(_timers)`. The disarm timer's `_task` has already
ended with `LookupError` (its callback tried to touch `active_app` in
a torn-down context), so `await timer._task` re-raises — exactly the
final frame in the user's traceback.

## Fix

Fix both issues in `tutor/gui.py` (the only file touched):

### 1. Marshal sink callbacks into the app's task context

Instead of mutating widgets directly from the dispatcher-task stack,
use `App.call_later(...)` so the body runs inside the app's own
task, where `active_app` is set.

Affected sink methods (they run on the dispatcher task today and touch
descendant widgets):

- `on_tutor_entry_removed` (`tutor/gui.py:419-439`) — calls
  `block.remove()` and `explanation.remove()` on descendants.
- `on_thread_list` (`tutor/gui.py:416-417`) — calls
  `_refresh_thread_list()` which itself calls `container.mount(...)`
  on descendants.
- For safety, review `on_tutor_entry`, `on_thread_chunk`,
  `on_thread_done` (`tutor/gui.py:378-414`) and apply the same pattern
  — they look like they've been working by luck, but they have the
  same shape (sink invoked from a backend async path, mutating
  descendant widgets). Start with the two that are proven broken; if
  the repro still crashes, apply to the rest.

Pattern:

```python
def on_tutor_entry_removed(self, anchor_id: str) -> None:
    self.call_later(self._apply_tutor_entry_removed, anchor_id)

def _apply_tutor_entry_removed(self, anchor_id: str) -> None:
    # existing body of on_tutor_entry_removed
    ...
```

`call_later` enqueues the callable onto the app's own message pump,
which runs it in the app task's context (with `active_app` set).

### 2. Track and cancel the disarm timer handle

Add two instance attributes next to the existing arming state
(`tutor/gui.py:319-320`):

```python
self._delete_arming_timer: Timer | None = None
self._thread_delete_arming_timer: Timer | None = None
```

(import `from textual.timer import Timer`)

In `_handle_line_delete_press` (`tutor/gui.py:476-485`), store the
handle:

```python
self._delete_arming_timer = self.set_timer(
    3.0, lambda aid=anchor_id: self._disarm_delete_if(aid)
)
```

In `_disarm_delete` (`tutor/gui.py:491-500`), cancel the handle:

```python
if self._delete_arming_timer is not None:
    self._delete_arming_timer.stop()
    self._delete_arming_timer = None
```

Mirror the same change for thread delete in
`_handle_thread_delete_press` (`tutor/gui.py:502-511`) and
`_disarm_thread_delete` (`tutor/gui.py:517-526`) using
`self._thread_delete_arming_timer`.

`Timer.stop()` is idempotent, so calling it when the timer has
already self-fired (the 3-second timeout path) is safe.

## Why both fixes are needed

- Fix #1 alone removes the original trigger: the dispatcher no longer
  raises `LookupError` inside `block.remove()`, so the widget tree and
  app state stay sane. That should stop the app from crashing.
- Fix #2 alone would not stop the crash — it only prevents a stray
  timer during shutdown. But it's worth doing: it eliminates the
  frame that shows up at the bottom of the traceback and prevents a
  similar crash at any future shutdown after a single-confirm cycle.
- Applied together, both the trigger and the downstream cleanup stop
  failing.

## Files to modify

- `tutor/gui.py` — only file touched.

## Verification

1. Run the GUI:
   ```bash
   ./scripts/bladerunner.sh
   ```
2. **Reproduce the bug first** without fixes (confirm crash on
   second click).
3. Apply the fix. Repeat: click a left-pane "Del" twice in quick
   succession. The line and its explanation should disappear and the
   app should keep running with no traceback.
4. Try the right-pane "Del" (thread delete) the same way — should
   also work cleanly.
5. Confirm the timeout disarm still works: click "Del" once, wait
   > 3 seconds, confirm the button label reverts to "Del" with no
   errors.
6. Confirm manual disarm: click "Del" on line A, then click "Ask"
   or another "Del" on line B before 3 seconds — line A should
   revert.
7. Exit the app (Ctrl+C / `q` binding) during each of the above
   states (armed, just-after-confirm, etc.) to make sure shutdown
   is clean.
8. Lint/type checks:
   ```bash
   uv run --frozen basedpyright tutor/gui.py
   uv run --frozen ruff check tutor/gui.py
   ```
