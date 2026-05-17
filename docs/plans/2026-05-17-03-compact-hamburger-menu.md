# Compact the hamburger menu panel

## Context

The hamburger menu's vertical footprint has grown: three full-height
menu rows (Show only explained / Switch dataset / Reset settings) at
`min-height: 44px` each, an audience config block, the Jump slider
block, and four separators. Total height lands around ~380px — a lot
of viewport for a panel that's used a few times per session.

The user asked to optimize this — reduce padding "or something." Goal:
visibly shorter panel without removing any item, restyling, or
breaking touch usability.

## Approach

CSS-only changes in `tutor/static/app.css`. Tighten the four padding /
spacing knobs that contribute the most height, plus drop the row
`min-height` from the WCAG-44 target to 36px — matching the existing
`.menu-btn` (line 45) and the bottom of Apple/Material's "comfortable
tap target" range (36-44px is the accepted range for non-primary
controls). Inputs stay at 32px (already touch-friendly).

### Numeric changes

`tutor/static/app.css`:

- **`.menu-panel`** (line 60): `padding: 0.25rem 0` → `padding: 0`
  (drops 8px top+bottom).
- **`.menu-item`** (lines 67-68): `padding: 0.5rem 0.75rem` →
  `padding: 0.375rem 0.75rem`; `min-height: 44px` → `min-height: 36px`
  (drops ~12px × 3 rows = ~36px total).
- **`.menu-sep`** (line 74): `margin: 0.25rem 0` → `margin: 0`
  (drops 8px × 4 separators = 32px).
- **`.menu-jump`** (lines 76, 79): `padding: 0.5rem 0.75rem` →
  `padding: 0.375rem 0.75rem`; `gap: 0.4rem` → `gap: 0.25rem`
  (drops ~6px).
- **`.menu-cfg`** (lines 85, 88): `padding: 0.5rem 0.75rem` →
  `padding: 0.375rem 0.75rem`; `gap: 0.3rem` → `gap: 0.2rem`
  (drops ~6px).

Expected total: roughly 80-90px shorter, ~25% reduction.

### What stays

- Inputs and slider keep their `height: 32px` / `min-height: 32px` —
  these are direct-touch targets and already at the lower bound.
- Font sizes unchanged (`.menu-jump-label` 0.9rem, `.cfg-label`
  0.85rem) — shrinking text hurts legibility more than it saves space.
- Panel `width: 15rem` and border stay — the user asked about height /
  padding, not width.
- Items stay in the same order; nothing is removed.

## Files to touch

- `tutor/static/app.css` — the eight property changes listed above. No
  HTML or JS changes.

## Verification

1. `make lint` passes (CSS isn't linted, but the rest of the suite
   still runs cleanly).
2. Manual browser check:
   - Open the hamburger menu on desktop. Confirm it's visibly shorter
     than before and all controls still fit without scroll.
   - Tap each row (Show only explained, Switch dataset, Reset
     settings) and confirm hit areas still feel comfortable on a
     phone-sized viewport (DevTools device emulation — iPhone or
     Pixel).
   - Confirm the Jump slider and the three audience inputs still
     render at full width and are easy to interact with.
   - Toggle dark mode — separators and borders still look right.
   - Open / close the menu a few times to confirm no layout shift
     elsewhere on the page (panel is `position: absolute`, so it
     shouldn't affect siblings, but worth a quick look).
