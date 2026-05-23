# Fix: vertical drag over a menu slider still changes its value on Android Chrome

## Context

Follow-up to `2026-05-23-14-slider-touch-action-pan-y.md`. That change added
`.menu-panel input[type="range"] { touch-action: pan-y; }` so a vertical drag
over a slider would scroll the scrollable hamburger menu instead of moving the
slider. On **Android Chrome** it still failed: the user restarted the server (so
the CSS was loaded), but the native range input keeps updating its value during a
vertical drag — and can snap to the touch x-position on the initial touchdown.
`touch-action: pan-y` lets the menu scroll but does not suppress that value
change, so CSS alone cannot fix it on Android.

The three affected sliders live in `#menu-panel`: `#jump-slider`,
`#opacity-slider`, `#fontsize-slider`.

## Change

`tutor/static/app.js` (slider setup block) — keep the `pan-y` rule and add a
touch **axis guard**, mirroring the existing tap-vs-drag pattern at
`app.js:311,344-350`.

- `makeSliderAxisGuard(slider)` records the start position/value on `touchstart`
  and classifies the gesture as `'x'` or `'y'` on the first `touchmove` past an
  8px slop (compare `|dx|` vs `|dy|`). Both listeners are passive.
- Each slider's existing `input` handler checks `guard.axis === 'y'` first; when
  vertical it re-applies the **start** value (`jumpScrollTo` / `applyOpacity` /
  `applyFontSize`) and returns, so the menu just scrolls and the value is
  unchanged. Horizontal drags, track taps, and the +/- buttons are untouched.

Timing is what makes it reliable: the passive `touchmove` listener sets the axis
before the browser's default action changes the value and fires `input`, so the
handler always knows the direction.

## Verification

1. `make lint` — required by `CLAUDE.md`.
2. Restart the server (the `?v=` cache-buster is fixed at startup, `web.py:659`),
   reload, then on Android Chrome (or Chrome DevTools touch emulation):
   - Open the menu so it scrolls. Vertical drag over a slider → menu scrolls,
     value unchanged. Horizontal drag → value changes as before. Track tap and
     +/- buttons still work.
   - `#jump-slider`: a vertical drag must not jump the reading position; a
     horizontal drag still jumps to the chosen sentence.
3. Desktop mouse: sliders behave exactly as before (guard only reacts to touch).

## Critical file

- `tutor/static/app.js` (slider setup block)
- `tutor/static/app.css` (keep the `touch-action: pan-y` rule)
