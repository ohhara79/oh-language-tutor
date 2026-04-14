# Lazy connect for `reopen_thread`

## Context

`ClaudeSDKClient.__init__()` is cheap — it only stores options (see
`.venv/lib/python3.14/site-packages/claude_agent_sdk/client.py:64-75`). The
expensive work happens in `__aenter__()` → `connect()`
(`client.py:95-205`): spawning the Claude CLI subprocess, starting a
persistent anyio task group, and running the initialize handshake (up to a
60s timeout).

`FollowupThreadPool.open_thread` in `tutor/thread_pool.py:69-111` already
defers connection — it only builds the system prompt and `_ActiveThread`;
the real subprocess is spawned in `send_message` on first use
(`thread_pool.py:147-153`).

`reopen_thread` at `tutor/thread_pool.py:113-138` is the odd one out: it
eagerly calls `ClaudeSDKClient(...).__aenter__()` on every reopen, even
when the user only wants to view past messages. The goal is to make
`reopen_thread` mirror `open_thread` — defer the subprocess spawn until
the first followup message is actually sent. Trade-off accepted: a
stale/expired resume session won't surface until first `send_message`
instead of at reopen time.

## Changes

### 1. Add `resume_session_id` to `_ActiveThread`

File: `tutor/thread_pool.py:31-39`

```python
@dataclass(slots=True)
class _ActiveThread:
    thread_id: str
    meta: ThreadMeta
    system_prompt: str
    client: ClaudeSDKClient | None = None
    task: asyncio.Task[None] | None = None
    resume_session_id: str | None = None   # NEW
```

When non-`None`, `_connect` will use it as the SDK's `resume=` option
instead of initializing a fresh session from `system_prompt`.

### 2. Make `reopen_thread` lazy

File: `tutor/thread_pool.py:113-138`

Drop the `ClaudeSDKClient(...)` construction and `__aenter__()` call.
Just record the intent to resume:

```python
async def reopen_thread(self, thread_id: str) -> None:
    meta = self._store.load_thread(thread_id)
    if meta is None:
        self._sink.on_error(f'thread {thread_id} not found on disk')
        return
    self._active[thread_id] = _ActiveThread(
        thread_id=thread_id,
        meta=meta,
        system_prompt='',
        resume_session_id=meta.session_id,
    )
    self._log.write(f'=== thread reopen thread_id={thread_id} ===\n')
```

No `try/except` needed here anymore — session-expired errors will surface
in `send_message` via the existing `failed to connect thread` error path
(`thread_pool.py:151-153`). The `ClaudeAgentOptions` / `resume` machinery
moves into `_connect`.

### 3. Teach `_connect` about resume

File: `tutor/thread_pool.py:199-208`

Pass the active thread's resume intent through:

```python
async def _connect(
    self,
    system_prompt: str,
    resume_session_id: str | None = None,
) -> ClaudeSDKClient:
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=self._model,
        allowed_tools=[],
        resume=resume_session_id,
    )
    client = ClaudeSDKClient(options=options)
    await client.__aenter__()
    return client
```

### 4. Update `send_message` call site

File: `tutor/thread_pool.py:147-153`

```python
if at.client is None:
    try:
        at.client = await self._connect(
            at.system_prompt,
            at.resume_session_id,
        )
    except Exception as exc:  # noqa: BLE001
        self._sink.on_error(f'failed to connect thread {thread_id}: {exc}')
        return
```

## Files touched

- `tutor/thread_pool.py` — only file changed.

No caller changes needed (`tutor/gui.py:657` just awaits
`pool.reopen_thread(...)`; signature is unchanged).

## Verification

1. `uv run --frozen basedpyright tutor/thread_pool.py` — type-check passes.
2. `uv run --frozen pytest` — existing tests pass.
3. Manual GUI smoke test:
   - Open a followup thread, send a message, hide it.
   - Reopen the thread → observe no subprocess spawn in the log (only
     `=== thread reopen ===`), thread contents render from disk.
   - Send a followup → verify the `_connect` path runs now, response
     streams, and `session_id` is preserved across turns.
   - Delete the on-disk `session_id` (or let it expire) and reopen →
     the first `send_message` should surface a
     `failed to connect thread ...` error, matching `send_message`'s
     existing behavior.
