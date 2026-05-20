# Don't auto-focus textarea after follow-up answer completes

## Context

In thread view, when the user asks a follow-up question and the streamed
answer finishes, focus is automatically moved back to the follow-up
textarea. The user reports that this is undesirable: after reading an
answer, users *usually* don't ask another follow-up, so the auto-focus
just scrolls/draws attention to a textarea they don't intend to use next.

The initial auto-focus when a thread is opened (so the user can start
typing their first message right away) is fine and should be preserved —
only the post-`thread_done` / post-`error` focus is unwanted.

## Change

File: `tutor/static/app.js`

In the `htmx:sseBeforeMessage` handler that re-enables the
`form.thread-compose` form after `thread_done` or `error`, drop the
`ta.focus()` call. Keep re-enabling the button and textarea
(`btn.disabled = false`, `ta.disabled = false`) so the user can still
type a follow-up if they want — they just have to click into the field
themselves.

Also update the block comment above the handler: remove the trailing
sentence "Focus the textarea after re-enabling so the user can
immediately type the next message." which no longer reflects behavior.

The initial-load focus at `tutor/static/app.js:326` (when a thread is
opened) is intentionally left as-is.

### Diff sketch

```js
// Re-enable the matching thread-compose form when its streamed reply
// completes or errors. We match by thread_id parsed from the thread_done
// payload's OOB selector (hx-swap-oob="outerHTML:#msg-stream-{thread_id}")
// so cross-thread navigation doesn't accidentally re-enable an unrelated
// form.
document.body.addEventListener('htmx:sseBeforeMessage', (evt) => {
    ...
    inputs.forEach((input) => {
        const form = input.closest('form');
        if (!form) return;
        const btn = form.querySelector('button');
        const ta = form.querySelector('textarea[name="text"]');
        if (btn) btn.disabled = false;
        if (ta) ta.disabled = false;
    });
});
```

## Verification

1. Open a thread that has at least one existing message.
2. Confirm the follow-up textarea is auto-focused on thread open
   (unchanged behavior).
3. Type a follow-up question and submit it.
4. While the answer streams, confirm the textarea is disabled.
5. When the answer finishes, confirm:
   - the textarea and submit button are re-enabled,
   - focus does **not** move to the textarea (it stays wherever it was,
     e.g. on the page body / last clicked element),
   - clicking into the textarea still works and lets the user type
     another follow-up.
6. Trigger an error path (e.g. by sending a message that fails) and
   verify the form is re-enabled without focus stealing.
