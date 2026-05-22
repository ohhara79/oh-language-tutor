# Tighten header (iteration 2): match button height to title

## Context

After the first round of header tightening (header vertical padding
`0.75rem` → `0.4rem`; `.menu-btn` shrunk to `padding: 0.15rem 0.45rem;
min-height: 0; font-size: 1.05rem` — see
`2026-05-22-02-tighten-header-spacing.md`), the header still feels loose
around the title. The hamburger button was visibly ~2× the height of
the title text, so the button drove the row height and the small title
floated in the middle with empty space above and below it.

Goal: shrink the button until it's roughly the same height as the title
text, and trim the header's own padding the rest of the way so the row
hugs that height.

## Where the remaining space comes from

All in `tutor/static/app.css`:

- `header { padding: 0.4rem 1rem; }` (line 15) — still ~6.4px of vertical
  padding on each side.
- `.menu-btn { padding: 0.15rem 0.45rem; ... font-size: 1.05rem; ... }`
  (lines 48-53) — glyph (~16.8px) + vertical padding (~4.8px) + border
  from inherited `.btn` (2px) ≈ ~23.6px. Title text (`font-size: 1rem`,
  line 35) is ~16px. The ~7-8px difference is what shows up as empty
  space above/below the title in the centered flex row.

## Change

Edit only `tutor/static/app.css`. Two further trims:

1. Halve the header's remaining vertical padding.
   - `header { padding: 0.4rem 1rem; }` → `header { padding: 0.2rem 1rem; }`

2. Bring the hamburger button down to title height — zero vertical
   padding, glyph at the same `1rem` as the title.
   - `.menu-btn { padding: 0.15rem 0.45rem; min-height: 0; font-size: 1.05rem; line-height: 1; }`
     → `.menu-btn { padding: 0 0.4rem; min-height: 0; font-size: 1rem; line-height: 1; }`

After this, the button's intrinsic height is roughly `1rem` glyph + 2px
inherited `.btn` border ≈ ~18px, matching the title's ~16px line box
much more closely. With header vertical padding of `0.2rem` on each
side, total header height drops to ~25-26px (from ~40-44px after
iteration 1, and from ~63px originally).

`.btn { min-height: 44px; }` (line 235) remains overridden by
`.menu-btn`'s `min-height: 0`. The `.header-row` flex container still
vertically centers both children, so the title and button stay aligned.
Menu-panel positioning (`right: 1rem` of header, line 58) is unaffected.

No HTML / template changes.

## Verification

- Reload the app in a browser; the header should be visibly thinner than
  iteration 1, with the title text and hamburger glyph roughly the same
  height and minimal empty space above/below.
- Click the hamburger — menu panel still opens at the same right-aligned
  position.
- Narrow the viewport to force title truncation; ellipsis still renders
  and the button stays on one line.
- `make lint`.
