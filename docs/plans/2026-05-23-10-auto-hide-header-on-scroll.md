# Auto-hide header on scroll down, show on scroll up

## Context

The sticky header (`<header>` in `tutor/templates/index.html:12`) holds the
view-dir title and the hamburger button. It stays pinned via
`position: sticky; top: 0;` in `tutor/static/app.css:18` and consumes ~2rem of
vertical space at all times. When the user is reading the raw-line stream, the
header isn't being interacted with and just eats screen real estate — most
noticeable on phone-sized viewports.

Apply the familiar mobile browser address-bar pattern: slide the header up out
of view when the user scrolls down (reading new content), bring it back when
the user scrolls up (intent to navigate, jump, or open the menu).

## Approach

A CSS class on `<header>` toggled by the existing scroll listener.

- **CSS**: add a hide state that slides the header off the top.

  ```css
  body:not(.view-picker) header {
      transition: transform 0.2s ease-out;
      will-change: transform;
  }
  body:not(.view-picker) header.is-hidden {
      transform: translateY(-100%);
  }
  ```

  Keep the existing `position: sticky; top: 0; z-index: 30;` rule. The
  translate moves the sticky box itself, so the menu panel (which is
  `position: absolute; top: 100%;` relative to the header — `app.css:54`) goes
  with it, which is fine because the menu won't be open while hiding (see
  below).

- **JS**: extend the existing scroll handler in `tutor/static/app.js:502` —
  do not add a second listener. Track `lastScrollY` and direction; toggle
  `header.is-hidden` based on direction, with these rules:

  - At top of page (`window.scrollY <= 4`): always show.
  - Menu open (`menuPanel.hidden === false`): always show.
  - Scrolling down and past a small threshold (delta > 6px): hide.
  - Scrolling up (delta < -6px): show.
  - Below the threshold: leave state unchanged (prevents jitter).

  Apply to both list and thread views — no view scoping needed. In thread view
  the window rarely scrolls (the conversation scrolls internally), so the
  listener is effectively a no-op there, and on entering thread view
  `window.scrollTo(0, 0)` (`app.js:250`) already resets to the show state.

- **Menu-open coupling**: in `setMenuOpen` (`app.js:111`), when opening, also
  remove `is-hidden` from the header. This guarantees the menu anchor is
  visible when it appears, and the scroll handler's "menu open → show" rule
  keeps it visible while the user interacts with the menu.

- **scroll-margin-top**: the existing `.line { scroll-margin-top: 4.5rem; }`
  (`app.css:210`) still applies. When the header is hidden, jump targets land
  slightly further from the top than necessary — acceptable; not worth adding
  conditional logic.

## Files to touch

- `tutor/static/app.css` — add the transition and `.is-hidden` rule to the
  sticky-header block (around line 18).
- `tutor/static/app.js` — extend the scroll listener at line 502 with the
  direction-tracking logic; add the `is-hidden` removal inside `setMenuOpen`
  at line 111.

No template changes; the `<header>` element already exists at
`tutor/templates/index.html:12`.

## Verification

1. `make lint` passes.
2. Run the app, open a dataset with enough lines to scroll.
3. Scroll down a few lines — header slides up smoothly and disappears.
4. Scroll up — header slides back into view immediately.
5. Scroll all the way to the top — header is visible and stays visible.
6. Scroll down to hide the header, then tap the menu button area: nothing
   should happen (button is hidden). Scroll up to bring it back, open the
   menu, then scroll the page — header (and therefore the menu) stays
   visible the whole time.
7. Open a thread, scroll within the conversation — header behavior unchanged
   (stays visible, since the window doesn't scroll).
8. Re-check on a narrow viewport (mobile width) — the gained vertical space
   when hidden is the desired outcome.
