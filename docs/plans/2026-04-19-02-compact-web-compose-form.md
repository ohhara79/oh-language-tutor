# Compact the web UI compose form (input + send side-by-side)

## Context

The thread compose form in the web UI stacked a tall (~88px, 2-row) textarea above a full-width "Send" button. This wasted vertical space at the bottom of the thread view. Goals:

1. Shrink the text input to a single-line height.
2. Place the Send button to the right of the input (same row), not below.
3. Make the Send button narrower than the default `.btn` width.

Only the compose area changes — message list, header, and delete button stay as they are.

## Files touched

- `tutor/templates/partials/thread_conversation.html` — textarea `rows` attribute.
- `tutor/static/app.css` — `.thread-compose`, `.thread-compose textarea`, and `.btn-send` rules.

No JS changes: `tutor/static/app.js` (Enter-to-send, IME guard, auto-clear on send) keys off the `form.thread-compose` selector and the textarea, both of which remain.

## Changes

### 1. `tutor/templates/partials/thread_conversation.html`

Textarea `rows="2"` → `rows="1"` so the initial rendered height is a single line.

### 2. `tutor/static/app.css`

`.thread-compose` — row layout:

- `flex-direction: column` → `flex-direction: row`.
- Add `align-items: stretch` so the button matches input height.
- `gap: 0.25rem` → `0.5rem` for a bit of breathing room between input and button.

`.thread-compose textarea` — single-line flex child:

- Remove `width: 100%`; add `flex: 1` to fill remaining horizontal space.
- `min-height: 88px` → `min-height: 44px` (matches `.btn` min-height).
- `padding: 0.75rem` → `padding: 0.5rem 0.75rem` so one line sits centered.
- `resize: vertical` → `resize: none` (`Shift+Enter` still inserts newlines via the existing JS handler).

`.btn-send` — narrower, no stacking margin:

- Drop `margin-top: 0.5rem`.
- Add `padding: 0.5rem 0.75rem` to override the wider `.btn` default (`padding: 0.5rem 1rem`).
- Add `flex-shrink: 0` so the button keeps its natural width when the textarea grows.

## Verification

1. Run the web UI and open a thread. Confirm:
   - Textarea renders as a single-line input at the bottom of the thread view.
   - Send button sits immediately to the right of the input, vertically aligned.
   - Send button is visibly narrower than before.
   - Enter submits; `Shift+Enter` inserts a newline; IME composition (Korean) still works (`app.js:204-214`).
   - After a successful send, the textarea clears and refocuses (`app.js:217-226`).
2. Check both light and dark themes — dark-mode rules at `app.css:246-248` don't touch `.btn-send`, so it remains consistent.
3. `make lint` passes.
