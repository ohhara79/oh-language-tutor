# Compose textarea: Enter-to-send + auto-clear

## Context

In thread-detail view, the compose form (`tutor/templates/partials/thread_conversation.html:20-27`) keeps the sent message in the textarea after submission, and Enter inserts a newline. Users want Enter to submit and the textarea to clear after a successful send.

## Change — `tutor/static/app.js` only

Add two delegated handlers:

```js
// Enter submits compose; Shift+Enter inserts newline; IME composition preserved.
document.body.addEventListener('keydown', (e) => {
    if (!(e.target instanceof HTMLTextAreaElement)) return;
    const form = e.target.closest('form.thread-compose');
    if (!form) return;
    if (e.key !== 'Enter' || e.shiftKey) return;
    if (e.isComposing || e.keyCode === 229) return;  // IME (e.g. Korean jamo)
    e.preventDefault();
    form.requestSubmit();
});

// Clear the compose textarea after a successful send.
document.body.addEventListener('htmx:afterRequest', (evt) => {
    const form = evt.target.closest && evt.target.closest('form.thread-compose');
    if (!form) return;
    if (!evt.detail || !evt.detail.successful) return;
    const ta = form.querySelector('textarea[name="text"]');
    if (ta) ta.value = '';
});
```

Key points:
- `e.isComposing` / legacy `keyCode === 229` guard prevents premature submit while committing Korean jamo.
- `form.requestSubmit()` goes through HTMX's form-submit hook — preserves `hx-post`, `hx-target`, `hx-swap`.
- Only clears on `evt.detail.successful` so failed sends keep the draft.
- No template or CSS change.

## Verification
1. `node --check tutor/static/app.js` — syntax.
2. `uv run --frozen ruff check tutor/ && uv run --frozen basedpyright tutor/` — green.
3. Manual: Enter submits + clears; Shift+Enter newline; IME composition doesn't submit; click Send still works; failed send keeps draft.

## Critical files
- `tutor/static/app.js`
