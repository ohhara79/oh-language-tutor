# Show Claude's answer being written, live

## Context

The web UI has two flows that call Claude. Neither updates the UI while
Claude is answering:

1. **Ask / thread send** — `tutor/thread_pool.py:_stream_response` already
   iterates `client.receive_response()` and emits `on_thread_chunk` per
   `AssistantMessage` block. It *looks* like streaming, but the SDK only
   yields a single complete `AssistantMessage` per turn — so the chunk
   handler fires exactly once at the end. No progress is visible.
2. **Explain** — `tutor/web.py:_run_explain` buffers the entire response
   into a list and returns it after `receive_response()` completes. No
   per-chunk SSE event at all. Worst offender because `--explain-model`
   defaults to `claude-opus-4-7`, which is slow.

`claude_agent_sdk` 0.1.63 supports token-level streaming via the
`StreamEvent` message type, gated by
`ClaudeAgentOptions(include_partial_messages=True)`. Each `StreamEvent`
wraps a raw Anthropic API event under `event` — for live text we care
about events shaped like
`{'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': '...'}}`.

Intended outcome: both flows render text token-by-token in the browser
via the existing SSE/HTMX OOB swap pipeline, while persistence and final
markdown rendering continue to use the canonical `AssistantMessage`
content.

## Approach

Re-use the existing thread streaming infrastructure
(`WebSink.on_thread_chunk` / `on_thread_done`, the `#sse-buffer` swap
target in `tutor/templates/index.html`, the `htmx:sseBeforeMessage`
re-enable logic in `tutor/static/app.js`). For Explain, mirror the
thread pattern: return an in-progress line fragment immediately, stream
deltas via SSE, finalize with the existing `entry_explained` event.

## Changes

### 1. Enable partial messages on the SDK

- `tutor/thread_pool.py:_connect` — add `include_partial_messages=True`
  to the `ClaudeAgentOptions`.
- `tutor/web.py:run_web` (`explain_options`) — same.

### 2. Stream thread tokens (Ask flow)

- `tutor/stream_util.py` (new) — `text_delta(event: StreamEvent) -> str | None`
  extracts incremental text from `content_block_delta` events. Returns
  `None` for any other shape.
- `tutor/thread_pool.py:_stream_response` — receive loop handles
  `StreamEvent` (calls `sink.on_thread_chunk` with the delta text) and
  `AssistantMessage` (extends `buf` for persistence). The chunk emission
  is no longer fired from the `AssistantMessage` branch.

No template / JS / SSE changes needed — `thread_chunk` and `thread_done`
events are already wired.

### 3. Stream the Explain flow

The Explain endpoint currently blocks the HTTP request for the entire
generation. Restructure to mirror the thread pattern:

- `tutor/web_sink.py` — add:
  - `on_explain_chunk(entry_id, chunk)` — broadcasts an `explain_chunk`
    SSE event with an OOB swap fragment
    `<span hx-swap-oob="beforeend:#explain-stream-{entry_id}">{escaped}</span>`.
  - `on_explain_aborted(entry)` — broadcasts an outerHTML OOB swap of
    `#line-{entry.id}` back to the unexplained variant.
  - `track_explain(task)` — adds an in-flight explain task to
    `_pending_explains` so `flush_pending_writes` can await it at
    shutdown.
  - `render_line` grows a `streaming: bool = False` parameter (implies
    `active`).

- `tutor/templates/partials/line.html` — add a third `streaming` branch
  that renders the empty `#explain-stream-{id}` container plus a muted
  "Explaining…" status line in place of the Explain/Delete buttons.
  Default `streaming` to `false` via `{% set streaming = streaming|default(false) %}`
  so the initial page render (which doesn't pass the flag) still works.

- `tutor/web.py` —
  - Replace `_run_explain` with `_stream_explain(ctx, entry, user_msg)`:
    opens a one-shot `ClaudeSDKClient(options=ctx.explain_options)`,
    forwards `StreamEvent` text deltas to `sink.on_explain_chunk`,
    accumulates `AssistantMessage.content` into a buffer, then on
    success persists via `tutor_store.update_explanation_async` and
    broadcasts `sink.on_entry_explained`. On failure or empty response
    it calls `sink.on_error` + `sink.on_explain_aborted` so the line
    rolls back to the unexplained variant for retry.
  - `/commands/explain` now spawns `_stream_explain` as
    `asyncio.create_task`, tracks it through `sink.track_explain`, and
    returns the streaming line fragment immediately.

- `tutor/templates/index.html` — add `explain_chunk,explain_aborted` to
  the `sse-swap` list on `#sse-buffer`.

- `tutor/static/app.css` — `.explain-stream` (pre-wrap, word-break)
  plus a blinking `::after` cursor on `.line.streaming .explain-stream`
  and a muted `.explain-status` style.

### 4. Authoritative text vs. partial deltas

Both flows derive the persisted text from `AssistantMessage`, not the
accumulated partial deltas. Partial deltas can in principle be
re-ordered / dropped on transport hiccups; `AssistantMessage` is the
canonical complete content the SDK guarantees.

## Verification

- `make lint` clean.
- `uv run --frozen pytest` — existing explain and thread-pool tests
  updated to drive the new code paths:
  - `make_text_delta(text)` fixture helper in `tests/conftest.py`.
  - `test_send_message_happy_path` seeds `StreamEvent`s before the
    `AssistantMessage` to assert the chunk path fires per delta.
  - The four `test_post_explain_*` cases now expect a 200 streaming
    response, await `ctx.sink.flush_pending_writes()`, then assert the
    final state (persisted explanation, or logged error + unchanged
    store).
  - `tests/test_stream_util.py` — unit tests for `text_delta`.
- Manual browser check:
  - Click **Explain** on a line — the section switches to a streaming
    placeholder with a blinking cursor, text arrives token-by-token,
    then the section snaps to the markdown-rendered final variant with
    Ask/Delete buttons. Refresh mid-stream still persists.
  - Send a message in a thread — tokens appear progressively in
    `#msg-stream-{thread_id}`; `thread_done` replaces the span with
    rendered markdown and re-enables Send.

## Critical files

- `tutor/thread_pool.py` (options + receive loop)
- `tutor/web.py` (`_stream_explain`, `/commands/explain` shape)
- `tutor/web_sink.py` (`on_explain_chunk`, `on_explain_aborted`,
  `track_explain`, `render_line(streaming=...)`)
- `tutor/stream_util.py` (`text_delta`)
- `tutor/templates/partials/line.html` (streaming variant)
- `tutor/templates/index.html` (`sse-swap` event list)
- `tutor/static/app.css` (`.explain-stream`, cursor, status)

## Out of scope

- Live markdown rendering of partials (jitter-prone; we render markdown
  only on completion, matching the existing thread behavior).
- Pre-flight token counters or "model thinking…" indicators.
- Cancelling an in-flight Explain from the UI.
