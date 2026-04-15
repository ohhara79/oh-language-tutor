# Plan: Two-click confirm for thread delete

## Context

Plan `docs/plans/2026-04-15-04-delete-line-and-stable-anchor-id.md` added a
two-click confirm to the **line** delete button (first click arms with
`Confirm?` label + `.armed` CSS + 3s disarm timer; second click deletes).
That plan is now merged in `tutor/gui.py`.

The **thread** delete button (`Del` in the right-pane thread sidebar) is
still single-click immediate (`tutor/gui.py:463-465`). A stray click wipes a
thread. The user wants the same two-click UX for thread delete.

Scope: UX-only change in `tutor/gui.py`. No data-model, storage, or command
changes — `DeleteThreadCmd` and its dispatcher stay as-is.

## Approach

Mirror the existing line-delete machinery with a parallel set for threads,
using a separate arming variable so the two states never collide:

1. **New instance var** next to `self._delete_arming_id` (`tutor/gui.py:315`):
   `self._thread_delete_arming_id: str | None = None`.

2. **New handler `_handle_thread_delete_press(thread_id, button)`** —
   exact mirror of `_handle_line_delete_press` (`tutor/gui.py:467-476`) but
   keyed on thread id, with `DeleteThreadCmd(thread_id=...)` and button
   label flipping `Del` ↔ `Confirm?`. Uses `self.set_timer(3.0, ...)` with
   the same 3s disarm window.

3. **New `_disarm_thread_delete_if(tid)` and `_disarm_thread_delete()`** —
   mirror of `tutor/gui.py:478-491`, querying `#delete-{arming}` (the
   existing thread delete button id) instead of `#line-delete-{arming}`.

4. **Rewire `on_button_pressed`** (`tutor/gui.py:451-465`):
   - `ask-` and `reopen-` branches: additionally call
     `self._disarm_thread_delete()` alongside the existing
     `self._disarm_delete()` — any unrelated action clears both arms.
   - `line-delete-` branch: `_handle_line_delete_press` stays, but prepend
     `self._disarm_thread_delete()` so arming a line disarms threads.
     Symmetric inside `_handle_thread_delete_press`: call
     `self._disarm_delete()` first so arming a thread disarms lines.
   - `delete-` branch: replace the immediate
     `self._cmd_queue.put_nowait(DeleteThreadCmd(...))` with
     `self._handle_thread_delete_press(tid, event.button)`.

5. **Clear arm on thread-list rebuild.** `_refresh_thread_list`
   (around `tutor/gui.py:625-636`) tears down and remounts `ThreadListItem`
   widgets, so an armed `Del` button disappears. Call
   `self._disarm_thread_delete()` at the top of `_refresh_thread_list` —
   also covers the sink-driven refresh that fires when a thread is deleted,
   so the arming id never points at a vanished button. (The 3s disarm
   timer would also clear it eventually, but resetting on refresh keeps
   state tight.)

6. **CSS** (inside `_APP_CSS`, after `tutor/gui.py:249-252`): add
   ```
   .thread-delete-btn.armed {
       background: $warning;
       color: $text;
   }
   ```
   Mirrors `.line-delete-btn.armed` (`tutor/gui.py:231-234`); reuses the
   existing `min-width: 5` on `.thread-delete-btn` which already
   accommodates the longer `Confirm?` label (same width as line delete).

## Files to modify

- `tutor/gui.py` — only file touched. New arming var, handler, two disarm
  helpers, CSS rule, rewire four button-press branches, disarm on thread
  list refresh.

## Verification

1. `uv run --frozen basedpyright` clean.
2. Launch: `tail -f somefile | uv run --frozen oh-language-tutor gui`.
3. Click `Del` on a thread → label flips to `Confirm?`, background turns
   warning color. Wait >3s → reverts to `Del`, nothing deleted.
4. Click `Del` again within 3s → thread deleted, sidebar refreshes.
5. Click `Del` on thread A, then `Del` on thread B → A disarms, B arms.
6. Click `Del` on a thread (arm), then click a line `Del` → thread
   disarms, line arms. Vice versa.
7. Click `Del` (arm), then click `Open` or `Ask` on anything → thread
   disarms, no delete.
8. Stream a new explanation while a thread `Del` is armed → thread list
   does not refresh unexpectedly; if a refresh does fire, the arm state
   clears cleanly (no stale id).
