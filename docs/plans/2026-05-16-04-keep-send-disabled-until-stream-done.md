# Keep Send disabled until the streamed reply finishes

## Context

The user observes that Send re-enables almost immediately after clicking it,
even though the assistant's reply takes several seconds to appear. They want
Send to remain disabled while the reply is being "prepared."

Root cause: `/commands/send_message` (`tutor/web.py:209-218`) returns as soon
as it spawns the background streaming task — it does **not** await the
assistant's reply. The actual text streams back via SSE
(`tutor/web_sink.py:98 on_thread_chunk`) and is finalized by `thread_done`
(`tutor/web_sink.py:102 on_thread_done`). `hx-disabled-elt` on the form only
covers the brief POST window, so the button springs back to enabled while
the SSE stream is still flowing.

We want one continuous busy state: from click → through the POST → through
the SSE chunks → until `thread_done` (or `error`) fires.

## Approach

Drive the loading visuals off the `:disabled` pseudo-class instead of the
form's `.htmx-request` class, so the visual state is governed by a single
property we can extend in JS.

- During the POST, `hx-disabled-elt="find button"` already sets
  `button.disabled = true` — unchanged.
- After the POST returns, the existing `htmx:afterRequest` handler in
  `tutor/static/app.js:243` re-asserts `button.disabled = true` so the
  button stays disabled through the SSE window.
- On `htmx:sseBeforeMessage` with type `thread_done` or `error`, find the
  thread-compose form for that thread (matched via its hidden
  `name="thread_id"` input — `thread_done`'s payload carries
  `id="msg-stream-{thread_id}"`, so we extract the id) and clear
  `button.disabled`.

The line-action buttons (Explain / Ask / Delete) only need their button
disabled for the POST duration, which `hx-disabled-elt` already provides —
so switching the CSS from `form.htmx-request .btn` to `.btn:disabled` is a
no-op for them. The CSS gets simpler in the process.

## Files to modify

### 1. `tutor/static/app.css`

Replace the existing block (the post-commit `form.htmx-request` rules):

```css
.btn .btn-label-busy { display: none; }
form.htmx-request .btn-label-idle { display: none; }
form.htmx-request .btn-label-busy { display: inline; }

.btn:disabled,
form.htmx-request .btn {
    cursor: not-allowed;
    color: #888;
    border-color: #ccc;
    background: rgba(128, 128, 128, 0.08);
}
.btn:disabled:hover,
form.htmx-request .btn:hover {
    background: rgba(128, 128, 128, 0.08);
}
```

with the simpler `:disabled`-only form:

```css
.btn .btn-label-busy { display: none; }
.btn:disabled .btn-label-idle { display: none; }
.btn:disabled .btn-label-busy { display: inline; }

.btn:disabled {
    cursor: not-allowed;
    color: #888;
    border-color: #ccc;
    background: rgba(128, 128, 128, 0.08);
}
.btn:disabled:hover {
    background: rgba(128, 128, 128, 0.08);
}
```

And in the dark-mode block, replace
`form.htmx-request .btn { color: #888; border-color: #555; }` with
`.btn:disabled { color: #888; border-color: #555; }` (drop the
`.btn:disabled,` comma — it now stands alone).

### 2. `tutor/static/app.js`

Modify the existing `htmx:afterRequest` thread-compose handler
(`app.js:243-252`) so that on a **successful** POST it keeps the button
`disabled`, and on a **failed** POST it clears `disabled` (otherwise the
button would be stuck disabled because we no longer rely on HTMX to clear
it after thread_done).

```js
document.body.addEventListener('htmx:afterRequest', (evt) => {
    const form = evt.target && evt.target.closest && evt.target.closest('form.thread-compose');
    if (!form) return;
    const btn = form.querySelector('button');
    if (!evt.detail || !evt.detail.successful) {
        if (btn) btn.disabled = false;
        return;
    }
    const ta = form.querySelector('textarea[name="text"]');
    if (ta) {
        ta.value = '';
        ta.focus();
    }
    if (btn) btn.disabled = true;
});
```

Add a new SSE listener that re-enables Send when the streamed reply
finishes or errors. We match the specific form by thread_id (extracted from
`thread_done`'s OOB swap payload) so cross-thread navigation doesn't
incorrectly re-enable an unrelated compose form:

```js
document.body.addEventListener('htmx:sseBeforeMessage', (evt) => {
    const type = evt.detail && evt.detail.type;
    if (type !== 'thread_done' && type !== 'error') return;
    const data = (evt.detail && evt.detail.data) || '';
    const match = data.match(/id="msg-stream-([^"]+)"/);
    const forms = match
        ? document.querySelectorAll(
            `form.thread-compose input[name="thread_id"][value="${CSS.escape(match[1])}"]`)
        : document.querySelectorAll('form.thread-compose input[name="thread_id"]');
    forms.forEach((input) => {
        const btn = input.closest('form')?.querySelector('button');
        if (btn) btn.disabled = false;
    });
});
```

### 3. `tutor/templates/partials/thread_conversation.html`

No change. `hx-disabled-elt="find button"` is still useful — it covers the
brief POST window even before our JS handler asserts the post-POST disabled
state.

## Verification

1. Restart the dev server.
2. Open a thread (Ask on an explained line), type a follow-up, click Send:
   - During POST: button shows **Sending…**, gray, `disabled` attribute
     present (as before).
   - **After POST returns**, button stays in the **Sending…**/gray state.
     Verify in DevTools that the button keeps `disabled` while
     `<span hx-swap-oob="beforeend:#msg-stream-…">` chunks are streaming
     into the assistant message div.
   - On `thread_done` (assistant message replaced with rendered markdown):
     button returns to idle **Send** state.
3. Press Enter in the textarea during the streaming window — no submission
   (browser refuses to submit a form whose default submit button is
   disabled).
4. Force an error path (e.g. raise in `pool.send_message` server-side) and
   confirm the button re-enables — both for POST failure (`afterRequest`
   with `successful=false`) and for streaming failure (SSE `error` event).
5. Confirm Explain / Ask / Delete still gray + label-swap during their
   POSTs — the CSS refactor should be a no-op for them since
   `hx-disabled-elt` already gives those buttons the `disabled` attribute
   during their requests.
6. `make lint`.
