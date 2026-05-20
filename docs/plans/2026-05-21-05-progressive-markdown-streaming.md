# Render markdown progressively during Explain/Ask streaming

## Context

When the user clicks **Explain** or **Ask**, the answer streams back in small text deltas. Today the UI shows those deltas as raw text (HTML-escaped, `white-space: pre-wrap`), so the partial result looks like raw markdown source — `**bold**`, `# heading`, bullets — until the stream completes, at which point the whole line/message snaps to fully-rendered HTML.

The user wants the mid-stream view to be rendered as markdown on a best-effort basis, accepting that some edge cases (e.g. half-open `**`, unclosed code fences) won't render cleanly. The goal is "better than current," not perfect.

## Approach

Re-render the **full accumulated text** on the backend on every chunk, and replace the container's `innerHTML` instead of appending raw text. This reuses the existing `render_markdown()` (Python `markdown` lib with CJK-safe emphasis preprocessing), so the mid-stream look matches the final look exactly — no visual jump at the end. Cost is fine for a local app: rendering and SSE payload are sub-ms per chunk.

This applies to both code paths that currently append raw chunks:
- `WebSink.on_explain_chunk` — used by the Explain button
- `WebSink.on_thread_chunk` — used by the Ask button (thread messages)

Rejected alternative: client-side JS markdown library (e.g. `marked.js`). It would avoid re-rendering on each chunk, but it introduces a new dependency and risks divergence between mid-stream rendering (JS lib) and final rendering (Python lib with custom CJK emphasis rules) — a jarring visual jump on completion.

## Files to modify

### `tutor/web_sink.py`

1. Add per-stream text buffers on `WebSink.__init__` (`tutor/web_sink.py:27`):
   ```python
   self._explain_buffers: dict[str, str] = {}
   self._thread_buffers: dict[str, str] = {}
   ```

2. Rewrite `on_explain_chunk` (`tutor/web_sink.py:129`) to accumulate, re-render, and replace `innerHTML`:
   ```python
   def on_explain_chunk(self, entry_id: str, chunk: str) -> None:
       accumulated = self._explain_buffers.get(entry_id, '') + chunk
       self._explain_buffers[entry_id] = accumulated
       rendered = render_markdown(accumulated)
       target = f'#explain-stream-{html.escape(entry_id)}'
       fragment = f'<div hx-swap-oob="innerHTML:{target}">{rendered}</div>'
       self._broadcast('explain_chunk', fragment)
   ```

3. Rewrite `on_thread_chunk` (`tutor/web_sink.py:125`) symmetrically, targeting `#msg-stream-{thread_id}`.

4. Clear the buffer on stream end so a future stream for the same id starts clean:
   - `on_entry_explained` (`tutor/web_sink.py:111`): `self._explain_buffers.pop(entry.id, None)`
   - `on_explain_aborted` (`tutor/web_sink.py:133`): same
   - `on_thread_done` (`tutor/web_sink.py:143`): `self._thread_buffers.pop(thread_id, None)`

### `tutor/static/app.css`

The `::after` cursor on `.explain-stream` (`tutor/static/app.css:204`) was designed for raw-text streaming. Once the container holds rendered markdown ending in a block element (`<p>`, `<h1>`, `<ul>`, etc.), the cursor lands on its own line below the content with `margin-left: 1px` — visually awkward.

Drop the `.line.streaming .explain-stream::after` rule and the unused `@keyframes explain-cursor-blink`. The existing **"Explaining…"** status text in `line.html:35` already signals activity. (No change needed for thread streaming — it never had a cursor.)

The `.explain-stream { white-space: pre-wrap; word-break: break-word; }` rule (`tutor/static/app.css:200`) can stay; `pre-wrap` is a no-op when the content is block-level HTML, and `word-break: break-word` still protects long CJK runs.

## Edge cases (accepted imperfections)

- **Unclosed `**bold**`**: regex requires a closing `**`, so half-typed bold renders as literal `**`. Snaps to bold once the closing pair arrives. Acceptable.
- **Unclosed code fence**: Python-markdown extends the code block to end-of-input, which is actually a reasonable preview.
- **List items mid-line**: `_insert_blank_before_lists` injects a blank line before a `-`/`*`/digit-dot marker, so lists render incrementally. Fine.
- **Trailing partial word inside emphasis**: may flicker between styled and unstyled as the closing token arrives. User explicitly accepted this kind of flicker.

## Verification

1. Start the app: `make run` (or whatever the project's run target is — see `Makefile`).
2. In the browser, click **Explain** on a line and watch the streaming output. Confirm that headings, bold, italics, lists, and inline code render progressively (not as raw `**` / `#` text).
3. Click **Ask**, send a message, and confirm the assistant reply also renders progressively.
4. Confirm that when streaming completes, there is no visual "snap" — the final rendered output looks identical to the mid-stream rendering.
5. Trigger an explain abort (e.g. by killing the network or forcing an error) and confirm the line rolls back cleanly with no leftover streaming buffer.
6. Run `make lint` to make sure typing/lint pass.
