# Skip textarea auto-focus when opening a follow-up thread

## Context

Clicking a follow-up in the thread list loads the conversation into
`#thread-conversation` and then auto-focuses the compose textarea
(`tutor/static/app.js:405`). When reopening an existing thread, the user
almost always wants to read the prior answer first — auto-focusing the
textarea scrolls the input into view and raises the mobile keyboard, which
fights that intent.

The same `#thread-conversation` swap is also produced by:

- The per-line "Ask" button (`tutor/templates/partials/line.html:9`) — a POST
  to `/commands/open_thread` that opens a brand-new thread. Focusing the
  textarea here is correct: the user just opened it to start typing.
- The Delete form inside a thread (`tutor/templates/partials/thread_conversation.html:2`)
  — returns the empty-state placeholder and is already handled by the
  separate `isEmpty` branch in the swap handler, so it doesn't focus anyway.

So the rule is: focus only when the swap came from a POST (Ask). Skip focus
on GET (follow-up thread link in `tutor/templates/partials/thread_list.html:5`).

## Approach

In the `htmx:afterSwap` handler at `tutor/static/app.js:389`, gate the
existing `ta.focus()` call by the request verb available on the htmx event
detail:

```js
const verb = evt.detail?.requestConfig?.verb;
if (verb !== 'get') {
    const ta = t.querySelector('form.thread-compose textarea[name="text"]');
    if (ta) ta.focus();
}
```

No template, server, or CSS changes. The `isEmpty` branch (delete-flow
return) is untouched.

## Files to touch

- `tutor/static/app.js` — single conditional inside the `t.id === 'thread-conversation'`
  branch of the `htmx:afterSwap` listener (around line 404).

## Verification

1. `make lint` passes.
2. Run the app and exercise each path that swaps `#thread-conversation`:
   - Click an existing follow-up in the thread list → conversation loads,
     textarea is **not** focused, page does not scroll to the input, mobile
     keyboard does not appear.
   - Press "Ask" on a line to open a new thread → textarea **is** focused
     (unchanged).
   - Inside a thread, send a message → unchanged (swap target is
     `#thread-messages-{id}`, not `#thread-conversation`).
   - Delete a thread while viewing it → still navigates back via the
     existing `isEmpty` branch.
