# Fix thread response not saved when stream is interrupted

## Context

User reports: "Sometimes, thread doesn't seem to be saved properly. I can see question only sometimes in the json file."

Threads store both user questions and assistant answers in JSON via `ThreadStore`. The user message is persisted immediately on send, but the assistant response is only persisted *after* the streaming query loop returns cleanly. When the stream is interrupted mid-flight — by app shutdown (event loop cancelling tasks), by an SDK-level error, or by any `asyncio.CancelledError` raised while `receive_response()` is pumping — the post-stream save code is skipped, leaving a thread on disk with a `user` message but no matching `assistant` message.

Goal: guarantee that whatever response text has been accumulated so far is persisted, even when the stream task is cancelled or fails partway through.

## Root cause

In `tutor/thread_pool.py` — `_stream_response` (currently lines 245–272):

```python
buf: list[str] = []
try:
    await at.client.query(text)
    async for msg in at.client.receive_response():
        ...
        buf.append(block.text)
        ...
except Exception as exc:  # noqa: BLE001
    self._sink.on_error(f'thread query failed: {exc}')
    return
finally:
    self._sink.on_thread_done(at.thread_id)

# ↓ only reached on clean success — skipped on CancelledError or after except-return
response = ''.join(buf).strip()
if response:
    at.meta.messages.append(ThreadMessage(role='assistant', text=response))
    self._store.save_thread(at.meta)
    self._log.write(f'[assistant] {response}\n')
```

Two problems:

1. `asyncio.CancelledError` is a `BaseException` (Python 3.8+), so it bypasses `except Exception`. The `finally` runs (so `on_thread_done` fires) but the post-block save code is unreachable because the exception keeps propagating.
2. The `except Exception` branch `return`s without saving, so any partial response already in `buf` is lost on mid-stream errors.

Context — `send_message` (line 175) saves the user message synchronously *before* spawning the stream task, which is why the question persists even when the answer does not.

## Fix

Move the persistence block into `finally` so it runs on every exit path (success, cancellation, exception), and drop the `return` in the `except` branch so `finally` still sees `buf`.

### File to modify

- `tutor/thread_pool.py` — `_stream_response` method (lines 245–272)

### New shape

```python
async def _stream_response(self, at: _ActiveThread, text: str) -> None:
    """Query Claude and stream the response to the sink."""
    if at.client is None:
        self._sink.on_error(f'thread {at.thread_id} has no active client')
        self._sink.on_thread_done(at.thread_id)
        return
    buf: list[str] = []
    try:
        await at.client.query(text)
        async for msg in at.client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        buf.append(block.text)
                        self._sink.on_thread_chunk(at.thread_id, block.text)
            elif isinstance(msg, ResultMessage):
                at.meta.session_id = msg.session_id
    except Exception as exc:  # noqa: BLE001
        self._sink.on_error(f'thread query failed: {exc}')
    finally:
        response = ''.join(buf).strip()
        if response:
            at.meta.messages.append(ThreadMessage(role='assistant', text=response))
            self._store.save_thread(at.meta)
            self._log.write(f'[assistant] {response}\n')
        self._sink.on_thread_done(at.thread_id)
```

Key points:
- The save is inside `finally`, so `CancelledError` (which is still re-raised after `finally`) does not skip it.
- `self._store.save_thread()` and `self._log.write()` are synchronous, so no await point inside `finally` gives cancellation another chance to abort the save.
- Removing `return` in the `except` arm lets the finally-save capture partial responses from mid-stream SDK errors.
- `_on_task_done` (lines 238–243) already ignores cancelled tasks, so no callback change is needed.
- `hide_thread` (lines 181–195) already awaits the task rather than cancelling it, so normal Escape / reopen flows were already fine; the fix specifically rescues the app-shutdown and error-mid-stream cases.

## Verification

1. Static: `uv run --frozen basedpyright tutor/thread_pool.py` — no new type errors.
2. Unit-ish manual test:
   - Run the app: `uv run --frozen <entrypoint>` (use the same command normally used to launch the tutor GUI).
   - Open a followup thread, type a long prompt that produces a slow multi-chunk response.
   - While chunks are still streaming, close the app (Ctrl+C or quit).
   - Inspect the thread's JSON under the threads store directory; confirm the `assistant` message is present with whatever text had been streamed so far.
3. Regression check: repeat without interrupting — confirm the full response is saved exactly once (not duplicated) and `on_thread_done` still fires for the GUI.
4. Optional: temporarily raise an exception from inside the `async for` loop and confirm any partial buffer is persisted.
