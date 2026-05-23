# Fix: dragging to scroll the hamburger menu changes slider values on touch screens

## Context

On small screens the hamburger menu (`#menu-panel`) is a vertically
scrollable popover (`overflow-y: auto`, `max-height: calc(100dvh - 4rem)` in
`tutor/static/app.css:59-73`). It contains three **horizontal** range
sliders:

- `#jump-slider` — jump to Nth sentence
- `#opacity-slider` — page opacity
- `#fontsize-slider` — content font size

On a touch screen, when the user presses on a slider and drags **vertically**
to scroll the menu open/closed, the native `<input type="range">` captures the
touch and changes its value instead of scrolling the menu.

There is **no custom JS drag/pan handler** for the menu — "panning" is just the
browser's native scroll of the overflow container. So the problem is purely
about which element consumes the touch gesture.

## Change

`tutor/static/app.css` — add one rule after `.menu-panel[hidden]`:

```css
.menu-panel input[type="range"] { touch-action: pan-y; }
```

`touch-action: pan-y` tells the browser that vertical-pan gestures over these
elements are scroll gestures it handles itself, so a vertical drag scrolls the
menu and does **not** move the slider. Horizontal drags are still delivered to
the slider, so dragging left/right still adjusts the value — important for
`#jump-slider`, which has no +/- buttons.

The descendant selector covers all three sliders and any future one, instead
of repeating the property on each id. `picker.html` loads the same `app.css`
and reuses `.menu-panel`, so it is covered too. CSS-only, no JS; mouse/desktop
behavior is unaffected by `touch-action`.

## Verification

1. `make lint` — required by `CLAUDE.md`.
2. Touch simulation (Chrome DevTools → Device Toolbar → phone preset) or a real
   device:
   - Open the menu so it overflows and is scrollable.
   - Press on a slider and drag **vertically** → menu scrolls, slider value
     unchanged.
   - Drag a slider **horizontally** → value still changes as before.
   - Confirm mouse/desktop drag of sliders is unchanged.

## Critical file

- `tutor/static/app.css` (one rule after line 74)
