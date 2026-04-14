# Fix follow-up thread: delayed/out-of-order replies

## Context

The user reports that follow-up thread replies appear delayed — they type a
question, see no reply, retype the same thing, and only then see a reply (often
accompanied by Claude saying "같은 질문이시네요" / "I already answered that").

`state/bladerunner/threads/tutor_thread_20260415001940_292_6239ed32.json` shows
the symptom: duplicate consecutive user messages with a single assistant reply
in between, and an assistant reply that references the *previous* topic even
though the newest user message is about something different.

Root causes (confirmed by reading `tutor/thread_pool.py` and `tutor/gui.py`):

1. **`FollowupThreadPool.send_message` does not serialize queries per thread**
   (`tutor/thread_pool.py:178`). It overwrites `at.task` with a new
   `asyncio.create_task(...)` without awaiting the prior one. Two concurrent
   `client.query()` calls on the same session cause replies to arrive in an
   unpredictable order, and the second query sees the first reply already in
   its context, making Claude respond with "same question".

2. **`OhLanguageTutorApp._reopen_thread` renders from disk synchronously**
   (`tutor/gui.py:483`). It calls `self._pool.load_thread_meta(thread_id)` and
   mounts messages before the dispatcher has processed any pending
   `HideThreadCmd` / `ReopenThreadCmd`. If a prior task is still in flight, the
   on-disk meta lacks the reply — the user sees a stale conversation.

3. **`action_hide_thread` fully closes the backend** (`tutor/gui.py:519`,
   `tutor/thread_pool.py:181`). Pressing Escape pops the thread from `_active`,
   awaits its task, and disconnects. When the user reopens, a brand-new
   `_ActiveThread` is built from disk — streaming chunks that arrived between
   hide and reopen are dropped (`tutor/gui.py:375`) and the session has to be
   re-resumed.

The combined effect: the user escapes or otherwise changes view while a reply
is in flight, sees stale disk state on reopen, retypes the same question, and
a concurrent/late response arrives saying "same question".

## Plan

### 1. Serialize queries per thread in the pool

**File:** `tutor/thread_pool.py`

In `send_message`, before creating a new `_stream_response` task, await the
prior task if one is still running. This guarantees `client.query()` is never
called concurrently on the same session and that replies are saved in the order
the queries were sent.

```python
async def send_message(self, thread_id: str, text: str) -> None:
    at = self._active.get(thread_id)
    if at is None:
        self._sink.on_error(f'thread {thread_id} is not active')
        return

    # Wait for any in-flight response to complete so queries serialize.
    if at.task is not None and not at.task.done():
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await at.task

    # ... existing lazy-connect block ...

    at.meta.messages.append(ThreadMessage(role='user', text=text))
    self._store.save_thread(at.meta)
    self._log.write(f'[user] {text}\n')
    at.task = asyncio.create_task(self._stream_response(at, text))
    at.task.add_done_callback(self._on_task_done)
```

### 2. Keep the backend alive on Escape (view-only hide)

**File:** `tutor/gui.py`

Change `action_hide_thread` so it only toggles the UI — it does **not** enqueue
`HideThreadCmd` and does **not** clear `_current_thread_id`. The `_ActiveThread`
and its in-flight task stay in the pool, streaming chunks continue to update
the already-mounted `_streaming_label` widget in the hidden container, and when
the user returns the reply is there.

```python
def action_hide_thread(self) -> None:
    self._thread_view_mode = 'list'
    self._show_list_mode()
    self._refresh_thread_list()
    # Backend thread stays active; streaming continues in the background.
```

### 3. Reopen of the already-current thread is a pure view toggle

**File:** `tutor/gui.py`

In `_reopen_thread`, if `thread_id == self._current_thread_id`, skip the
disk-load and re-render. Just show the conversation pane again. Input enable
state follows task state: if `_streaming_label is not None`, a task is in
flight and input stays disabled (on_thread_done will re-enable it).

```python
def _reopen_thread(self, thread_id: str) -> None:
    if self._current_thread_id == thread_id:
        self._show_conversation_mode()
        inp = self.query_one('#thread-input', Input)
        if self._streaming_label is None:
            inp.disabled = False
        inp.focus()
        self._scroll_left_pane_to_anchor(
            self._pool.load_thread_meta(thread_id).anchor_idx
            if self._pool and self._pool.load_thread_meta(thread_id) else -1
        )
        return

    # ... existing flow for switching to a different thread ...
```

(The existing path, which enqueues `HideThreadCmd` for the previous thread
and renders the new one from disk, is correct for *switching* threads — the
previous thread has no special claim on streaming state once the user moves
to another one.)

### 4. Use in-memory meta when reopening a different thread with an active task

**File:** `tutor/thread_pool.py` + `tutor/gui.py`

Add a small helper on the pool:

```python
def peek_meta(self, thread_id: str) -> ThreadMeta | None:
    """Return in-memory meta if active, else load from disk."""
    at = self._active.get(thread_id)
    if at is not None:
        return at.meta
    return self._store.load_thread(thread_id)
```

In `_reopen_thread` (the non-same-thread branch), replace
`self._pool.load_thread_meta(thread_id)` with `self._pool.peek_meta(thread_id)`
so the GUI renders whatever the in-memory meta has (including any chunks that
were appended after the task finished but before its disk write landed).

## Files to modify

- `tutor/thread_pool.py` — serialize in `send_message`, add `peek_meta`
- `tutor/gui.py` — simplify `action_hide_thread`, fast-path in `_reopen_thread`,
  use `peek_meta`

## Verification

1. **Reproduce the original bug (regression check):**
   - `uv run --frozen python -m tutor ...` with a running source
   - Open a thread, send a question, press **Escape** immediately, then
     reopen the thread from the list. Expected: the reply streams into the
     open conversation view; no duplicate prompt needed.
2. **Duplicate submit guard:**
   - Open a thread, send a question, before the reply arrives, attempt to
     submit the same text again by any means available (the input should be
     disabled). If the submit does reach the backend, the serialization fix
     ensures it's processed *after* the first reply completes — no concurrent
     `client.query` calls, no out-of-order replies.
3. **Type checker & linter:**
   - `uv run --frozen basedpyright tutor/`
   - `uv run --frozen ruff check tutor/`
4. **Existing thread still readable:**
   - Reopen `tutor_thread_20260415001940_292_6239ed32` from the thread list —
     messages render in the order they appear in the JSON.
