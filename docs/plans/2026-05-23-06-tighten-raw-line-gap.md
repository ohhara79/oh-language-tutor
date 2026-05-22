# Reduce gap between raw texts in the raw text list view

## Context

The raw text list view (the main `#stream-pane` in `tutor/templates/index.html`) renders one `.line` per entry. Currently each entry has noticeable vertical whitespace between items, which the user wants to tighten.

The vertical space between two adjacent raw-text items comes from three sources in `tutor/static/app.css`:

- `.line` (lines 204–208): `padding: 0.25rem 0` → 0.25rem above + 0.25rem below = **0.5rem of `.line` padding** between siblings.
- `.raw-toggle` (lines 214–232): `padding: 0.75rem 0.5rem` → 0.75rem top + 0.75rem bottom inside each item = **1.5rem of internal padding** per item (adjacent items contribute 0.75rem each to the visible gap).
- `min-height: 44px` on `.raw-toggle` — a touch-target floor that keeps short lines from collapsing.

So the visible gap between two raw text items is roughly: `0.75rem` (bottom of upper `.raw-toggle`) + `0.25rem` (`.line` bottom padding) + `1px` border + `0.25rem` (`.line` top padding) + `0.75rem` (top of lower `.raw-toggle`) ≈ **2rem + 1px**.

## Recommended change

Tighten both layers so the gap halves without losing the divider or touch-target safety:

In `tutor/static/app.css`:

- `.line` — change `padding: 0.25rem 0` → `padding: 0` (removes 0.5rem between items).
- `.raw-toggle` — change `padding: 0.75rem 0.5rem` → `padding: 0.25rem 0.5rem` (removes 1rem per item).
- Keep `min-height: 44px` so single short lines still have a comfortable touch target (the inner text just centers within it).
- Keep the 1px `border-top` divider so items remain visually separated.

Net visible gap drops from ~2rem to ~0.5rem + 1px border.

## Critical files

- `tutor/static/app.css` — lines 204–232 (the two padding declarations above).

## Verification

1. `uv run --frozen` start the app (per project conventions) and load the index view.
2. Confirm the raw text list shows tighter spacing between consecutive `.line` items.
3. Click a raw line to expand its detail — verify `.line-detail` still has breathing room (it has its own `padding: 0.25rem 0.25rem 0.75rem`, unchanged).
4. Check a line whose text is very short — the `.raw-toggle` should still be ≥ 44px tall (touch-target preserved).
5. `make lint` — no Python changes, but run for hygiene.
