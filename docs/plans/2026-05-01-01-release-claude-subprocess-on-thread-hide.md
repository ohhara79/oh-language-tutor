# Release `claude` subprocesses when threads are no longer in use

## Context

While `oh-language-tutor` runs, `claude` CLI subprocesses accumulate and
persist until the app exits. Each followup thread lazily spawns one (via
`ClaudeSDKClient.__aenter__()` inside `FollowupThreadPool._connect`) on
its first `send_message`, and the subprocess is owned by
`_ActiveThread.client` until `pool.hide_thread` / `pool.delete_thread` /
`pool.close_all` runs. Two leak paths:

- **Web UI** — `tutor/static/app.js`'s Back button and `popstate` only
  pop the JS view stack. `/commands/hide_thread` is defined in
  `tutor/web.py:209-214` but nothing calls it. Every thread the user
  opens and sends a message in keeps a subprocess alive for the
  remainder of the session.
- **TUI** — `action_hide_thread` (Escape) only flips the view to the
  list. Switching to a *different* thread (`_open_new_thread` /
  `_reopen_thread` slow path) already queues a `HideThreadCmd` for the
  previous one, so this only leaks the thread the user last viewed
  before quitting/Escaping.

User's stated rule: "if the thread is closed and there is no
processing (waiting the reply from claude), the claude session can be
safely terminated." I.e. defer the disconnect until any in-flight
stream has completed; do not cancel mid-stream just because the user
navigated away.

## Approach

Introduce a `hide_when_idle` flow that matches the rule: if the thread
is idle, disconnect now; if a stream is in flight, mark it for
deferred disconnect and let the existing `_stream_response.finally`
block tear down the subprocess after the reply has been persisted.

### Backend — `tutor/thread_pool.py`

1. Add `hide_pending: bool = False` to `_ActiveThread`.
2. Add `hide_when_idle(thread_id)`:
   - If no `_ActiveThread` for the id → no-op.
   - If `at.task is None or at.task.done()` → delegate to `hide_thread`
     (immediate disconnect, existing 2 s grace).
   - Otherwise set `at.hide_pending = True`.
3. In `send_message`, clear `at.hide_pending = False` before scheduling
   the new stream task — re-engaging the thread cancels any pending
   idle-hide.
4. In `_stream_response`'s `finally` block (after `on_thread_done`): if
   `at.hide_pending`, pop the entry from `_active`, disconnect the
   client, and log `=== thread close (deferred) ... ===`. The
   disconnect runs from inside the task itself (not via
   `hide_thread`) to avoid an `asyncio.shield(at.task)` self-deadlock.
   `at.client` may still be `None` if the initial connect attempt
   failed before assigning, so guard explicitly.

`delete_thread` keeps calling `hide_thread` (immediate, with the
existing 2 s grace) — deletes shouldn't wait. `close_all` is unchanged
and still iterates `hide_thread` at shutdown.

### Web — `tutor/web.py` and `tutor/static/app.js`

- `tutor/web.py`: change `/commands/hide_thread` to call
  `pool.hide_when_idle` instead of `pool.hide_thread`.
- `tutor/static/app.js`:
  - When `htmx:afterSwap` populates `#thread-conversation` with a real
    thread, capture `thread_id` from the form's hidden input
    (`partials/thread_conversation.html`) and stash it on the pushed
    stack entry: `push('thread', {thread_id})`. If the swap occurs
    while already in thread view, update `current().thread_id` so the
    new thread's id is what gets hidden on Back.
  - Add a `notifyHideThread(threadId)` helper that POSTs
    `/commands/hide_thread` with `keepalive: true`, fire-and-forget.
    Double-calls are a safe no-op on the backend.
  - Call `notifyHideThread` from `pop()` and from the `popstate`
    handler when the popped entry was a thread view.
  - On the delete-thread auto-back path (the empty-state branch of
    `htmx:afterSwap`), clear `current().thread_id` first so the
    triggered `history.back()` doesn't double-hide.

### TUI — `tutor/tui.py`

- `_dispatch_commands` `HideThreadCmd` case: dispatch to
  `pool.hide_when_idle` (was `pool.hide_thread`). All three call sites
  (`_open_new_thread`, `_reopen_thread` slow path, and the new
  `action_hide_thread`) carry "user is leaving this thread"
  semantics, which matches `hide_when_idle`.
- `action_hide_thread`: queue `HideThreadCmd(thread_id=self._current_thread_id)`
  before flipping the view. Don't clear `_current_thread_id` so
  re-clicking the same thread still hits the fast path in
  `_reopen_thread`.

### Known minor edge case (not fixed)

If the user Escapes/Backs during streaming and re-engages the same
thread *before* the stream finishes (without sending a new message),
`hide_pending` stays set and the subprocess is disconnected when the
reply lands. The persisted reply is intact (saved in
`_stream_response.finally` before the deferred-hide block), but the
live-streaming view is lost. Sending a new message clears the flag
and avoids this. Adding a "currently viewing" flag would fully fix
it; revisit if reported.

## Files modified

- `tutor/thread_pool.py` — `_ActiveThread`, new `hide_when_idle`,
  `send_message`, `_stream_response.finally`.
- `tutor/web.py` — `/commands/hide_thread` route.
- `tutor/static/app.js` — track `thread_id` on the view stack; POST
  hide on pop.
- `tutor/tui.py` — dispatcher mapping for `HideThreadCmd`;
  `action_hide_thread` queues it.
- `tests/test_web.py` — `_FakePool` gains `hide_when_idle`.
- `tests/test_tui_dispatch.py` — `_RecordingPool` renames
  `hide_thread` → `hide_when_idle` and assertions update accordingly.

## Verification

1. `make lint` — basedpyright + ruff clean.
2. `uv run --frozen pytest tests/` — full suite passes.
3. **Web manual**: start the web UI; in another shell run
   `watch -n1 'pgrep -af claude | wc -l'`.
   - Open thread A, send a message, wait for the reply — count: +1.
   - Press Back — within ~2 s the count returns to baseline.
   - Open thread B, send a message, press Back *during* streaming —
     count stays elevated until the stream completes, then drops back.
     Confirm the assistant reply is persisted under
     `state_dir/threads/<thread_id>.json`.
   - Re-enter thread A, send another message — works (resumes via
     `meta.session_id`); count rises by 1 then drops on Back.
   - Delete a thread from inside thread view — auto-back works,
     subprocess gone, no errors.
4. **TUI manual**: same `pgrep` watch.
   - Open thread, send message, wait, Escape — count drops back.
   - Open thread, send message, Escape *during* streaming — count
     stays until stream done, then drops.
   - Open thread A, send, switch to thread B — A's subprocess
     disconnects after A's stream completes (confirm via
     `=== thread close (deferred) ... ===` in the log).
5. **Shutdown**: Ctrl-C the app while a thread has `hide_pending=True`
   and an in-flight stream — `close_all` still calls `hide_thread`
   (immediate, 2 s grace), so cleanup completes without hanging.
