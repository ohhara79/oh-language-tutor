# Extend in-flight loading state to the thread-compose Send button

## Context

Commits `36fa3fe` and `e8de0ff` added an in-flight loading state to the four
per-line action buttons (Explain, Ask, two Deletes): the wrapping form gets
`hx-disabled-elt="find button"`, the inner `<button>` carries
`btn-label-idle` / `btn-label-busy` spans, and CSS in `tutor/static/app.css`
uses `form.htmx-request .btn` to gray + swap the label during the request.

The Send button in the thread-compose area
(`tutor/templates/partials/thread_conversation.html:22-29`) calls Claude
(`tutor/web.py:208 send_message → ctx.pool.send_message`) and can take
several seconds, but currently shows no in-flight feedback. The user wants
the same treatment.

## Approach

Apply the same pattern with a one-file change. The CSS rules
(`form.htmx-request .btn`, `form.htmx-request .btn-label-busy`, …) added in
the previous commits already match — no CSS work needed.

A nice property to call out: when Send is `disabled` mid-request, pressing
Enter in the textarea also stops working. The Enter handler at
`tutor/static/app.js:232-240` calls `form.requestSubmit()`, which per HTML
spec refuses to submit while the form's default submit button is disabled.
So no JS change is needed to prevent double-sends via the keyboard either.

The textarea itself stays enabled so the user can keep typing/drafting while
the previous message is in flight; only the Send action is blocked.

## Files to modify

### `tutor/templates/partials/thread_conversation.html` (lines 22-29)

Before:

```html
<form class="thread-compose"
      hx-post="/commands/send_message"
      hx-target="#thread-messages-{{ meta.thread_id }}"
      hx-swap="beforeend">
  <input type="hidden" name="thread_id" value="{{ meta.thread_id }}">
  <textarea name="text" rows="1" placeholder="Ask a follow-up..." required></textarea>
  <button type="submit" class="btn btn-send">Send</button>
</form>
```

After:

```html
<form class="thread-compose"
      hx-post="/commands/send_message"
      hx-target="#thread-messages-{{ meta.thread_id }}"
      hx-swap="beforeend"
      hx-disabled-elt="find button">
  <input type="hidden" name="thread_id" value="{{ meta.thread_id }}">
  <textarea name="text" rows="1" placeholder="Ask a follow-up..." required></textarea>
  <button type="submit" class="btn btn-send">
    <span class="btn-label-idle">Send</span>
    <span class="btn-label-busy">Sending…</span>
  </button>
</form>
```

That's the entire change. No CSS, no JS, no backend.

## Verification

1. Restart the dev server.
2. Open a line with an explanation → click **Ask** to open a thread.
3. Type a follow-up question and click **Send**:
   - Button label switches to **Sending…** during the request
   - Button turns gray, cursor is `not-allowed`
   - DevTools: the `<button>` has the `disabled` attribute while the request
     is in flight
   - Clicking Send again is a no-op
   - Pressing Enter in the textarea is also a no-op (browser refuses to
     submit a form whose default submit button is disabled)
   - On response, the textarea auto-clears via the existing
     `htmx:afterRequest` handler (`app.js:243-252`) and the button returns
     to its idle "Send" state
4. Toggle OS dark mode and re-confirm the gray state is still visibly
   distinct.
5. `make lint` — template-only change; should remain green.
