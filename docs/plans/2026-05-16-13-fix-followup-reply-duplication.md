# Fix follow-up answer duplication in the thread UI

## Context

When a user asks a follow-up question inside an open thread, the streamed assistant reply renders incorrectly: the previous turn's answer reappears in the new turn's slot (or the new tokens get appended on top of the previous answer). A page reload renders correctly from the persisted store, confirming the bug is purely a DOM/streaming issue, not a data issue. See the user's screenshot — two turns show visually identical assistant replies, which is impossible from the stored data.

### Root cause

After a streamed turn finishes, `WebSink.on_thread_done` (`tutor/web_sink.py:138-147`) replaces the streaming placeholder with the markdown-rendered final reply — but the replacement div **keeps the same `id="msg-stream-{thread_id}"`**:

```python
fragment = (
    f'<div id="msg-stream-{html.escape(thread_id)}" '
    f'class="msg assistant" hx-swap-oob="outerHTML">{rendered}</div>'
)
```

When the user asks the next question in the same thread, `send_message_result.html` (`tutor/templates/partials/send_message_result.html:2`) appends another empty `<div class="msg assistant" id="msg-stream-{thread_id}"></div>` via `hx-swap="beforeend"`. The DOM now contains **two** elements sharing that id: the previous (fully rendered) reply and the new empty placeholder.

HTMX's `hx-swap-oob="<strategy>:<selector>"` (used in `on_thread_chunk`, `on_thread_done`) resolves the target with `querySelectorAll`, so it swaps into **every** matching element. Result:

- Streamed chunks for turn 2 get appended to **both** divs (raw, html-escaped — visible mid-stream as escaped text after the old rendered answer).
- The final `on_thread_done` outerHTML swap replaces **both** divs with the new rendered reply, so the previous turn's answer slot now shows the new turn's reply instead. Both displayed messages end up identical.

Reload rebuilds the DOM from stored data via `partials/thread_conversation.html`, where historical assistant messages render as `<div class="msg assistant">…</div>` without the streaming id (`thread_conversation.html:18`), so the collision doesn't exist and the data displays correctly.

The fix is to make the finalized assistant div stop carrying `id="msg-stream-{thread_id}"` once streaming completes, so the next turn's placeholder is the only matching element.

## Approach

Strip the `id` attribute from the `on_thread_done` replacement fragment, and use HTMX's explicit OOB target syntax (`outerHTML:<selector>`) to point the swap at the placeholder. Update the client JS regex that extracts `thread_id` from the `thread_done` SSE payload so it reads the selector instead of the now-absent id attribute.

This is the minimal change: no schema changes, no per-turn id counter, and no template changes for placeholders or historical rendering.

## Changes

### 1. `tutor/web_sink.py` — `on_thread_done`, lines 138-147

Replace:

```python
def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
    rendered = render_markdown(last_assistant) if last_assistant else ''
    fragment = (
        f'<div id="msg-stream-{html.escape(thread_id)}" '
        f'class="msg assistant" hx-swap-oob="outerHTML">{rendered}</div>'
    )
    self._broadcast('thread_done', fragment)
```

with:

```python
def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
    rendered = render_markdown(last_assistant) if last_assistant else ''
    target = f'#msg-stream-{html.escape(thread_id)}'
    fragment = (
        f'<div class="msg assistant" '
        f'hx-swap-oob="outerHTML:{target}">{rendered}</div>'
    )
    self._broadcast('thread_done', fragment)
```

The finalized assistant div no longer carries the streaming id, so it cannot collide with the next turn's placeholder. The explicit `outerHTML:#msg-stream-{thread_id}` target still finds and replaces the currently-streaming placeholder.

### 2. `tutor/static/app.js` — `htmx:sseBeforeMessage` handler, line 346

The handler extracts `thread_id` from the `thread_done` payload to re-enable that thread's compose form. The current regex looks for `id="msg-stream-…"`, which goes away with change #1. Replace:

```javascript
const match = data.match(/id="msg-stream-([^"]+)"/);
```

with a regex against the OOB selector (or a `data-` attribute — selector is fine since it's already in the payload):

```javascript
const match = data.match(/#msg-stream-([^"\s]+)/);
```

This still pulls the thread_id out of both the new `thread_done` payload (`hx-swap-oob="outerHTML:#msg-stream-{tid}"`) and is robust to surrounding whitespace/quoting. The fallback path (when no match) already re-enables all forms — unchanged.

The `error` branch in the same handler emits a toast (`partials/toast.html`), which targets `#toast-container` — it never contains `#msg-stream-`, so the fallback path still triggers there as before.

## Critical files

- `tutor/web_sink.py` — modify `on_thread_done` (the only producer of the colliding id).
- `tutor/static/app.js` — update the SSE handler regex.

No template changes; no changes to `tutor/thread_pool.py`, `web.py`, or `partials/send_message_result.html`.

## Verification

1. `make lint` — no type errors.
2. Run the dev server (`uv run --frozen` per `CLAUDE.md`) and open a thread.
3. Ask Q1 in a fresh thread; wait for the streamed reply to fully render.
4. Without reloading, ask Q2. Confirm:
   - Q2's reply streams into the correct (new) slot only.
   - Q1's reply remains visible and unchanged.
   - After streaming completes, Q1 and Q2 both show their own distinct replies.
5. Ask Q3 to confirm the fix holds across multiple turns in one session.
6. Reload — DOM should match what was shown before reload (same content, no drift).
7. Inspect DOM mid-stream after Q1 completes and again after Q2's placeholder is inserted: there must be exactly one element with `id="msg-stream-{thread_id}"` (the active placeholder), never two.
