# Fix: vertical drag over a menu slider still changed its value on Android Chrome

## Context

Third attempt at the issue from `2026-05-23-14` and `2026-05-23-15`. The
hamburger menu (`#menu-panel`) is a vertically scrollable popover with three
horizontal range sliders (`#jump-slider`, `#opacity-slider`, `#fontsize-slider`).
Dragging vertically over a slider to scroll the menu also changed its value.

Prior attempts: `touch-action: pan-y` (14) let the menu scroll but Android Chrome
still changed the value; an axis guard whose revert lived in the `input` handler
(15) still failed. **Root cause of 15:** once a vertical drag starts scrolling,
the browser cancels the slider's pointer and it stops firing `input`. The value
had already changed on the first touch (axis still undecided → applied), and no
later `input` fired to revert it, so the change stuck.

## Change

`tutor/static/app.js` — replace `makeSliderAxisGuard` + the three `input`
handlers with one helper `guardSlider(slider, apply)` that classifies the gesture
from **touch** events (which keep firing during a scroll) instead of relying on
`input`:

- Track `axis` (`'x'` adjust / `'y'` scroll / `null` undecided) from
  touchstart/touchmove past an 8px slop.
- Commit a value only for a horizontal drag or a stationary tap; **restore the
  start value on `touchend`/`touchcancel`** for a vertical scroll — this is the
  piece attempt 15 lacked.
- The `input` handler holds the slider at the start value while the gesture is
  undecided or vertical (no flash, no change), and applies live for horizontal
  drags and for mouse/keyboard (no touch events → applies as before).

`apply(value)` per slider reuses existing functions (`jumpScrollTo`,
`applyOpacity`, `applyFontSize`). The +/- step buttons are untouched. The
`touch-action: pan-y` rule in app.css stays (it enables the scroll).

## Verification

1. `make lint` — required by `CLAUDE.md`.
2. **Restart the server** (`?v=` cache-buster is fixed at startup, web.py:659),
   reload. On Android Chrome or Chrome DevTools touch emulation:
   - Menu open and scrollable: vertical drag over a slider → menu scrolls, value
     unchanged after release. Horizontal drag → adjusts. Tap → sets. +/- work.
   - `#jump-slider`: vertical drag must not move the reading position.
3. Desktop mouse + keyboard: unchanged.

## Feasibility note

If Android Chrome still changes the value after this, the native
`<input type="range">` cannot coexist with touch-scroll reliably and the fallback
is a custom JS-driven slider (larger change).

## Critical files

- `tutor/static/app.js` (slider setup block)
- `tutor/static/app.css` (keep `touch-action: pan-y`)
