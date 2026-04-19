# Un-stick thread-detail compose form

## Context

In the web UI thread-detail view, the follow-up textarea and Send button are pinned to the viewport bottom (`position: sticky; bottom: 0`). While reading a long thread the compose form hovers over the message text and obstructs it. The user wants the compose form to flow at the natural end of the thread content and scroll with it.

## Approach

Remove the sticky positioning from `.thread-compose` so it lays out as a normal block element at the end of the conversation. Drop the backdrop styles that only existed to mask content scrolling beneath the pinned form, and shrink the body's bottom padding that was reserved to prevent the sticky form from covering content.

## Files to modify

- `tutor/static/app.css`

### Edits in `tutor/static/app.css`

1. `.thread-compose` rule: remove these properties:
   - `position: sticky;`
   - `bottom: 0;`
   - `background: Canvas;`
   - `padding-bottom: env(safe-area-inset-bottom, 0);` (only needed to clear the iOS home indicator when glued to the viewport)

   Keep `padding-top: 0.5rem`, the flex layout, and the gap — those still provide the small visual separation from the last message.

2. Dark-mode block: remove `.thread-compose { background: #1a1a1a; }`. That override existed solely so the sticky form would mask scrolling content in dark mode.

3. `body` rule: change `padding: 0 1rem 5rem;` to `padding: 0 1rem 1rem;`. The `5rem` bottom reserve was there to keep the sticky form from covering the last line; once the form scrolls with content it is no longer needed.

No HTML/template or JS changes are required — `partials/thread_conversation.html` already places the compose form at the end of the conversation container, which is exactly where it should render once the sticky rule is removed.

## Verification

1. Run the web mode locally and open the UI in a browser.
2. Open a thread with enough messages to force the conversation pane to exceed one viewport.
3. Confirm:
   - While scrolling up and down through the thread, the textarea + Send button no longer float over the message text.
   - The compose form sits at the bottom of the thread content and scrolls along with it.
   - Submitting a follow-up still posts via htmx and appends the new message to `#thread-messages-<id>` as before (regression check that removing sticky did not touch form wiring).
   - Toggle the system color scheme (or DevTools "Emulate prefers-color-scheme: dark") and verify the compose area still reads cleanly in dark mode without the former background fill.
4. Run `make lint` before declaring done.
