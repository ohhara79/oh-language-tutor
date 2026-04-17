# Fix: thread send doesn't update UI / stale thread list

## Context

After sending a message in a thread, the user reports:
1. The Claude response appears in `state/*/tutor.log` but is not visible in the web UI.
2. No new thread file appears to be created (symptom, not root cause — the file IS on disk).

Two bugs cooperate to produce these symptoms:

### Bug A — streamed response is wiped at end of stream

`WebSink.on_thread_done` (`tutor/web_sink.py:89-98`) emits an OOB swap that replaces the streamed `#msg-stream-{id}` div with an **empty** placeholder:

```python
fragment = f'<div id="msg-stream-{html.escape(thread_id)}" class="msg-stream done" hx-swap-oob="outerHTML"></div>'
```

At the moment the response finishes streaming, the accumulated chunks in `#msg-stream-{id}` are replaced with nothing. The user sees the answer appear and then vanish.

### Bug B — no `thread_list` SSE broadcast after save

`_stream_response` in `tutor/thread_pool.py` persists the thread file after the user message (line 298) and after the assistant response (line 321), but never calls `self._sink.on_thread_list(...)`. Consequences:

- A brand-new thread never appears in the per-line inline list or the orphan list until a page reload. This creates the illusion that the thread file wasn't created.
- Existing threads' message counts and first-question headings (`thread_heading` helper) never update live.

## Fix

### 1. Protocol: extend `on_thread_done`

Add a `last_assistant` parameter so `WebSink` can render the final message with markdown in its OOB replacement.

**`tutor/types.py`** (`OutputSink` Protocol):
```python
def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
    ...
```

**`tutor/sink.py`** (no-op stub):
```python
def on_thread_done(self, thread_id: str, last_assistant: str) -> None:  # noqa: ARG002
    pass
```

**`tutor/gui.py`** (TUI already buffers `_streaming_text` internally, ignores new param):
```python
def on_thread_done(self, thread_id: str, last_assistant: str) -> None:  # noqa: ARG002
    self.call_later(self._apply_thread_done, thread_id)
```

### 2. `WebSink.on_thread_done` — render markdown in replacement

```python
def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
    rendered = render_markdown(last_assistant) if last_assistant else ''
    fragment = (
        f'<div id="msg-stream-{html.escape(thread_id)}" '
        f'class="msg assistant" hx-swap-oob="outerHTML">{rendered}</div>'
    )
    self._broadcast('thread_done', fragment)
```

- The OOB `outerHTML` swap replaces the old stream div (containing raw chunk spans) with a properly-classed `.msg.assistant` div whose innerHTML is the markdown-rendered final text.
- `render_markdown` is already imported at the top of `web_sink.py`.
- The `_broadcast` newline-stripping is safe: markdown output has whitespace only between HTML tags (or inside `<pre>` where it matters). For robustness we could switch to base64/data-URI encoding later, but the current pipeline handles `render_markdown` output for `partials/line.html` already.

### 3. `_stream_response` — broadcast `thread_list` after each save

In `tutor/thread_pool.py`:

```python
at.meta.messages.append(ThreadMessage(role='user', text=text))
await self._store.save_thread_async(at.meta)
self._log.write(f'[user] {text}\n')
self._sink.on_thread_list(self._store.list_threads())   # NEW
```

```python
finally:
    response = ''.join(buf).strip()
    if response:
        at.meta.messages.append(ThreadMessage(role='assistant', text=response))
        await self._store.save_thread_async(at.meta)
        self._log.write(f'[assistant] {response}\n')
        self._sink.on_thread_list(self._store.list_threads())   # NEW
    self._sink.on_thread_done(at.thread_id, response)          # updated call
```

Update the four existing `on_thread_done` call sites in `_stream_response` to pass the text (or `''` on the early-return failure paths where no assistant text exists).

### 4. `_stream_response` — also broadcast on connect-fail paths

To heal from a failed new-thread attempt (ghost thread in UI), add `on_thread_list` to the existing failure branches before `on_thread_done`:

```python
self._sink.on_error(f'failed to connect thread {at.thread_id}: {exc}')
self._sink.on_thread_list(self._store.list_threads())   # NEW
self._sink.on_thread_done(at.thread_id, '')
return
```

Same shape in the resume-fail replay path.

## SSE-client interaction summary

- After first send: SSE `thread_list` fires → client `#thread-list` innerHTML replaced → `distributeThreads()` re-runs → the new thread row appears under its anchor line with `thread_heading` = first question.
- After assistant response: SSE `thread_list` fires again → msg count updates. SSE `thread_done` fires → streamed span replaced with markdown-rendered `.msg.assistant` div; user continues to see the answer.

## Verification

1. `uv run --frozen ruff check tutor/` + `uv run --frozen basedpyright tutor/` — green.
2. Unit-render the new `on_thread_done` fragment with a sample markdown string; confirm the OOB replacement contains the rendered HTML and the right id/class.
3. Launch server, open a thread via Ask, send a question:
   - Response streams in and stays visible after completion.
   - The thread appears in the per-line inline list immediately (not after page reload).
   - Once assistant reply lands, the list heading flips from `anchor_raw` to the user's first question; message count updates.
4. Connection error path: simulate by (temporarily) pointing the SDK at an invalid binary; confirm the error toast fires, no ghost thread remains in the list.

## Critical files
- `tutor/types.py` (protocol signature)
- `tutor/sink.py` (base stub)
- `tutor/gui.py` (TUI impl — accept param, ignore)
- `tutor/web_sink.py` (render markdown in replacement)
- `tutor/thread_pool.py` (pass text + broadcast thread_list)

## Out of scope
- No change to disk format or `ThreadStore`.
- No change to web UI templates or JS — existing `distributeThreads()` handles the resulting SSE updates.
- TUI streaming behavior unchanged (still uses its internal buffer).
