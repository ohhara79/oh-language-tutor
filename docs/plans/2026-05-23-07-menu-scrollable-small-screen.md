# Make hamburger menu usable on small screens

## Context

`#menu-panel` is an absolutely-positioned dropdown that contains five
controls (filter toggle, jump slider, opacity slider, font-size slider,
audience config). On small/short viewports (phones in particular) the
panel's natural height exceeds the viewport, and because the panel has
no `max-height` or scroll behavior, the bottom controls fall off the
screen and cannot be reached or scrolled into view. The page body
itself doesn't scroll the panel either, since the panel is
`position: absolute` on the header.

The goal: when the menu would overflow the viewport, let the menu
itself scroll, and prevent horizontal overflow on very narrow screens.
No new controls, no responsive redesign — just bound the panel to the
visible viewport.

## Change

Edit `.menu-panel` in `tutor/static/app.css` (lines 54–65) to add three
properties:

- `max-height: calc(100dvh - 4rem);` — cap the panel to the viewport
  height, leaving room for the header above. `dvh` (dynamic viewport
  height) correctly accounts for mobile browser chrome (URL bar
  showing/hiding); `vh` would over- or under-shoot.
- `overflow-y: auto;` — when content exceeds the cap, scroll inside
  the panel instead of bleeding off screen.
- `max-width: calc(100vw - 2rem);` — cheap insurance against
  horizontal overflow if the viewport is narrower than `15rem + 1rem`
  (~256px). On normal phones (375px+) this is a no-op.

That's the whole change — about three CSS lines in one rule. No HTML
or JS edits required; existing toggle/close behavior in
`tutor/static/app.js:107-127` already works fine.

## Files

- `tutor/static/app.css` — extend the `.menu-panel` rule at line 54.

## Verification

1. Run the app (`make run` or the project's normal start command) and
   open it in a desktop browser.
2. Resize the browser window to a narrow/short size (e.g., DevTools
   device toolbar → iPhone SE, or just a short window ~500px tall).
3. Click the hamburger button. Confirm:
   - The menu opens fully within the visible viewport.
   - When the content is taller than the viewport, the menu scrolls
     internally and all controls (including the audience config at
     the bottom) are reachable.
   - The panel does not extend off the right edge on narrow viewports.
4. Resize back to a tall desktop window and confirm the menu still
   opens at its natural height with no scrollbar (no regression).
5. `make lint` (no Python touched, so this is just hygiene).
