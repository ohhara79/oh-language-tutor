# Enlarge the "Follow-ups" heading font

## Context

The `.line-threads-heading` label added in
`docs/plans/2026-05-16-15-followups-heading.md` rendered at `0.85rem` with
uppercase + letter-spacing. Against the much larger explanation body
(`1.5rem`) and thread anchor lines (`1.25rem`), it read as a tiny annotation
and was harder to notice than intended. Bump the heading up to `1.1rem` so it
holds its own as a section label.

## Approach

One-line CSS tweak: change the `font-size` declaration in
`.line-threads-heading` from `0.85rem` to `1.1rem`. Keep everything else
(uppercase, weight, letter-spacing, color, dark-mode override) unchanged.

## Changes

### `tutor/static/app.css` — `.line-threads-heading`

Change `font-size: 0.85rem;` to `font-size: 1.1rem;`.

## Critical files

- `tutor/static/app.css` — sole change.

## Verification

1. `make lint`.
2. Reload the web UI; expand an explained line that has at least one
   follow-up thread. Confirm the "FOLLOW-UPS" heading is noticeably larger
   than before but still clearly subordinate to the explanation body and the
   anchor text in the thread items below it.
3. Toggle dark mode and confirm the color override still reads well.
