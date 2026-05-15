# Also disable the compose textarea while Send is disabled

## Context

Commit `134ba7c` kept the Send button disabled across the POST and the
SSE-streamed reply. The user reports they can still submit by pressing
**Enter** in the textarea during that window, bypassing the disabled
button.

Root cause: the keydown handler at `tutor/static/app.js:232-240` calls
`form.requestSubmit()` with no submitter argument. Per the HTML spec, that
form points to no specific submit button, so the "default submit button is
disabled → abort" rule does not apply, and HTMX's submit handler does not
gate on the button's disabled state either. So Enter still fires a request
even when the visible button is disabled.

Fix per the user's suggestion: disable the textarea in lockstep with the
button. A disabled `<textarea>` doesn't dispatch `keydown` (and the user
can't type into it), so Enter can no longer trigger a second submit, and
the busy state is also visually clearer.

## Approach

Manage `textarea.disabled` alongside `button.disabled` in the three
existing thread-compose JS hooks in `tutor/static/app.js`, and add minimal
CSS so the disabled textarea reads as visibly busy (matching the gray
button).

Lifecycle:

| Event | Button | Textarea |
| --- | --- | --- |
| `htmx:beforeRequest` (new handler) | (HTMX disables via `hx-disabled-elt`) | disable |
| `htmx:afterRequest` success | keep disabled | keep disabled, clear value |
| `htmx:afterRequest` failure | re-enable | re-enable |
| `htmx:sseBeforeMessage` `thread_done` / `error` | re-enable | re-enable, focus |

Focus is restored only after the textarea is re-enabled (you can't focus a
disabled textarea), so the user lands ready to type the next message right
as the reply finishes streaming — preserving the UX of the prior version
where `ta.focus()` ran in `afterRequest`.

## Files to modify

### 1. `tutor/static/app.js`

Add a new `htmx:beforeRequest` listener just above the existing
`htmx:afterRequest` handler:

```js
// When a Send starts, disable the textarea so pressing Enter during the
// POST + SSE-streamed reply window can't bypass the disabled button via
// form.requestSubmit().
document.body.addEventListener('htmx:beforeRequest', (evt) => {
    const form = evt.target && evt.target.closest && evt.target.closest('form.thread-compose');
    if (!form) return;
    const ta = form.querySelector('textarea[name="text"]');
    if (ta) ta.disabled = true;
});
```

Update the existing `htmx:afterRequest` handler so it also manages
`textarea.disabled` (and drops the now-unsafe `ta.focus()` — disabled
textareas can't receive focus; focus moves to the SSE-done handler):

```js
document.body.addEventListener('htmx:afterRequest', (evt) => {
    const form = evt.target && evt.target.closest && evt.target.closest('form.thread-compose');
    if (!form) return;
    const btn = form.querySelector('button');
    const ta = form.querySelector('textarea[name="text"]');
    if (!evt.detail || !evt.detail.successful) {
        if (btn) btn.disabled = false;
        if (ta) ta.disabled = false;
        return;
    }
    if (ta) ta.value = '';
    if (btn) btn.disabled = true;
});
```

Update the existing `htmx:sseBeforeMessage` handler so it also re-enables
the textarea and restores focus when the reply finishes:

```js
document.body.addEventListener('htmx:sseBeforeMessage', (evt) => {
    const type = evt.detail && evt.detail.type;
    if (type !== 'thread_done' && type !== 'error') return;
    const data = (evt.detail && evt.detail.data) || '';
    const match = data.match(/id="msg-stream-([^"]+)"/);
    const inputs = match
        ? document.querySelectorAll(
            `form.thread-compose input[name="thread_id"][value="${CSS.escape(match[1])}"]`)
        : document.querySelectorAll('form.thread-compose input[name="thread_id"]');
    inputs.forEach((input) => {
        const form = input.closest('form');
        if (!form) return;
        const btn = form.querySelector('button');
        const ta = form.querySelector('textarea[name="text"]');
        if (btn) btn.disabled = false;
        if (ta) {
            ta.disabled = false;
            ta.focus();
        }
    });
});
```

### 2. `tutor/static/app.css`

Add a disabled style for the compose textarea so it matches the button's
gray "busy" appearance, just after the existing `.thread-compose textarea`
block near line 187:

```css
.thread-compose textarea:disabled {
    cursor: not-allowed;
    color: #888;
    background: rgba(128, 128, 128, 0.08);
}
```

No dark-mode override needed — the rgba background and `#888` color already
read fine on both palettes (it's the same scheme used for `.btn:disabled`).

## Why not just guard in the keydown handler?

A one-line `if (form.querySelector('button')?.disabled) return;` in the
Enter handler would block the Enter bypass too, and is simpler. But it
would leave the textarea visually active during a multi-second streaming
window, which is a weaker "this is busy" signal — the user picked the
disable-textarea approach explicitly. Disabling the textarea also blocks
typing-then-pasting into a fresh send window, which is the natural chat
UX. We're going with the user's suggestion.

## Verification

1. Restart the dev server.
2. Open a thread, type a message, click **Send**:
   - Button: **Sending…** + gray + `disabled`
   - Textarea: gray + `disabled` (DevTools: `disabled` attribute present)
   - Try pressing **Enter** in the textarea — no submission (textarea won't
     even accept keydown; focus probably shifts elsewhere on disable).
3. When the streamed reply finishes (`thread_done`): both button and
   textarea become enabled; focus lands in the textarea so the next
   message can be typed immediately.
4. Type and press **Enter** for the next message — normal submission.
5. Force a POST failure → both re-enable.
6. Switch threads mid-stream — the unrelated thread's compose stays in its
   own state (we match by `thread_id` from the `msg-stream-…` payload).
7. `make lint`.
