# Fix right-pane thread: dispatcher stalls, questions silently dropped

## Context

User reports: intermittently, questions asked from the right pane produce no
reply. Crucially, when this happens **the user's question is not written to
`tutor.log` either** — so the code never reaches
`tutor/thread_pool.py:184` (`self._log.write(f'[user] {text}\n')`).
Restarting the app clears the state and it works again. The user can't
reliably reproduce a specific trigger; it happens after normal use.

That rules out a UI-render regression and points at the **command dispatcher
getting wedged**.

### Why the dispatcher wedges

`_dispatch_commands` (`tutor/gui.py:838–861`) is a single loop that
`await`s each pool call before pulling the next command:

```python
case SendMessageCmd():
    await pool.send_message(cmd.thread_id, cmd.text)
case HideThreadCmd():
    await pool.hide_thread(cmd.thread_id)
```

Both `pool.send_message` (`tutor/thread_pool.py:150–152`) and
`pool.hide_thread` (`tutor/thread_pool.py:198–200`) internally do:

```python
if at.task is not None and not at.task.done():
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await at.task
```

That await has **no timeout**. `at.task` is a `_stream_response` task
that calls `await at.client.query(text)` and iterates
`at.client.receive_response()`. If Claude's transport hangs (network
wobble, SDK bug, resumed session that never replies), the stream task
never completes, and every subsequent `send_message`/`hide_thread` call
in the dispatcher blocks forever behind it. Cmd queue entries pile up
behind the stuck await — the user types questions, sees their `You: …`
bubble (that's mounted directly from `on_input_submitted`, not through
the dispatcher), and nothing else happens. Nothing is logged because
`send_message` never reaches its log lines. Restarting the app throws
away the stuck task, so it "works again."

The same wedge also explains why `on_thread_done` never fires to
re-enable the input — the task truly is not done.

## Approach

Two small, independent changes:

### 1. Move per-thread serialization **into** the stream task

`tutor/thread_pool.py` — restructure `send_message` so the dispatcher
returns almost immediately. The "wait for the previous reply to finish"
hop happens *inside* the newly-spawned task, not on the dispatcher:

```python
async def send_message(self, thread_id: str, text: str) -> None:
    at = self._active.get(thread_id)
    if at is None:
        self._sink.on_error(f'thread {thread_id} is not active')
        return
    prev_task = at.task
    at.task = asyncio.create_task(
        self._stream_response(at, text, prev_task)
    )
    at.task.add_done_callback(self._on_task_done)


async def _stream_response(
    self,
    at: _ActiveThread,
    text: str,
    prev_task: asyncio.Task[None] | None,
) -> None:
    if prev_task is not None and not prev_task.done():
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await prev_task

    if at.client is None:
        # ... existing lazy-connect + resume-fallback block, moved here ...

    at.meta.messages.append(ThreadMessage(role='user', text=text))
    self._store.save_thread(at.meta)
    self._log.write(f'[user] {text}\n')

    buf: list[str] = []
    try:
        await at.client.query(text)
        async for msg in at.client.receive_response():
            # ... existing body ...
    ...
```

Key properties:

- `send_message` now does O(1) synchronous work, so the dispatcher never
  wedges on it — `HideThreadCmd`, `ReopenThreadCmd`, `DeleteThreadCmd`
  still run promptly even if a prior stream is stuck.
- Serialization per thread is preserved: the new task awaits `prev_task`
  before issuing its own `client.query`.
- The `[user]` log write still happens before `client.query`, so if the
  question reaches the pool at all it's visible in `tutor.log` —
  makes future occurrences diagnosable.
- The lazy connect moves into `_stream_response` alongside the existing
  resume-fallback path; that block already assumes it runs in the same
  task as the query, so it co-locates naturally.

### 2. Cap `hide_thread`'s wait for a stuck task

`tutor/thread_pool.py` — `hide_thread` currently does an unbounded
`await at.task`. If the task is wedged, Escape / list-view toggles feel
dead and `delete_thread` (which calls `hide_thread`) inherits the hang.
Add a short timeout; if the task doesn't complete we cancel it — the
`_stream_response` `finally` block already tolerates `CancelledError`
and persists whatever was buffered:

```python
async def hide_thread(self, thread_id: str) -> None:
    at = self._active.pop(thread_id, None)
    if at is None:
        return
    if at.task and not at.task.done():
        try:
            await asyncio.wait_for(asyncio.shield(at.task), timeout=2.0)
        except TimeoutError:
            at.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await at.task
        except Exception:  # noqa: BLE001
            pass
    if at.client is not None:
        await self._disconnect(at.client)
    self._log.write(f'=== thread close thread_id={thread_id} ===\n')
```

## Files to modify

- `tutor/thread_pool.py` — `send_message`, `_stream_response` (new
  `prev_task` param, absorb lazy-connect + serialization), `hide_thread`
  (bounded wait + cancel on timeout).
- `tutor/gui.py` — **no changes needed**; the dispatcher's
  `await pool.send_message(...)` is now fast, and `await
  pool.hide_thread(...)` is bounded.

## Verification

1. **Static checks:**
   - `uv run --frozen basedpyright tutor/`
   - `uv run --frozen ruff check tutor/`
2. **Happy path unchanged:**
   - Launch via `scripts/bladerunner.sh`, open a thread, ask a question,
     confirm reply streams into the right pane and persists to disk.
     Ask a follow-up; confirm it waits for the first reply (no
     interleaving in the on-disk JSON).
3. **Simulate a stuck stream (repro of the reported bug):**
   - Temporarily add `await asyncio.sleep(60)` at the top of the
     `async for msg in at.client.receive_response():` loop, OR pull
     the network after `client.query`.
   - Open a second thread / ask another question. **Expected:** the
     `[user] …` line appears in `tutor.log` immediately; the stuck
     thread's reply never arrives, but the new question's dispatcher
     path isn't blocked. Escape / thread-list still respond.
4. **Hide while streaming:**
   - Start a reply, press Escape immediately — list view shows within
     ~2 s even if the stream task is hung; any partial reply is
     persisted via the existing `_stream_response` `finally`.
5. **No regression of `f7d4ada`:** double-click a left-pane DEL while
   streaming, then quit — no `LookupError: active_app` traceback.
