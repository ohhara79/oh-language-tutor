# Tighten header: title + hamburger spacing

## Context

The page header (`tutor/templates/index.html` lines 12-18) shows the
view-directory title on the left and a hamburger menu button on the right.
The header currently feels visually heavy because of generous vertical
padding around the row and because the hamburger button enforces a
minimum size that is noticeably larger than its glyph.

Goal: reduce the empty space around the title and inside the hamburger
button so the header is more compact, without changing layout structure or
the menu behavior.

## Where the empty space comes from

All in `tutor/static/app.css`:

- `header { padding: 0.75rem 1rem; }` (line 15) — ~12px of empty space
  above and below the row.
- `.menu-btn { padding: 0.25rem 0.6rem; min-height: 36px; font-size: 1.2rem; }`
  (lines 48-53) — the 1.2rem glyph at line-height 1 is ~19px, plus 8px of
  vertical padding ≈ 27px of content, but `min-height: 36px` forces the
  button ~9px taller than its content needs. Horizontal padding (~9.6px
  each side) also widens the button beyond what the glyph requires.

The title itself (`.view-dir-label`, lines 33-46) has no padding of its
own; its perceived "empty space" is the header padding plus the size
mismatch with the larger hamburger button.

## Change

Edit only `tutor/static/app.css`. Two small tweaks:

1. Shrink the header's vertical padding so the row hugs the title.
   - `header { padding: 0.75rem 1rem; }` → `header { padding: 0.4rem 1rem; }`

2. Tighten the hamburger button so it's sized to its glyph, not to a
   touch-target minimum.
   - `.menu-btn { padding: 0.25rem 0.6rem; min-height: 36px; font-size: 1.2rem; line-height: 1; }`
     → `.menu-btn { padding: 0.15rem 0.45rem; min-height: 0; font-size: 1.05rem; line-height: 1; }`

Dropping `min-height` to `0` lets the button's intrinsic content height
drive its size (this overrides the `.btn { min-height: 44px; }` default
at line 235, which `.menu-btn` already overrides today). Slightly
lowering the glyph from 1.2rem to 1.05rem brings the button closer in
visual weight to the 1rem title text.

No HTML or template changes. Menu panel positioning (`.menu-panel`,
line 55) is anchored to `right: 1rem` of the header, so reducing the
button's intrinsic size does not move the menu.

## Verification

- Run the app and open the view-picker (`/`) and a per-view page in a
  browser.
- Confirm the header bar is shorter than before, the title and hamburger
  are vertically centered, and clicking the hamburger still opens the
  menu panel at the same position.
- Resize the browser narrow enough to truncate the title; confirm the
  ellipsis still appears and the hamburger stays on one line.
- `make lint` (pure-CSS change, but run per CLAUDE.md before declaring
  done).
