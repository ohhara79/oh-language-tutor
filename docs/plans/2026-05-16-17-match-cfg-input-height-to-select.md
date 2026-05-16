# Match Learning / Native input height to Level select

## Context

In the per-line config row (`Learning`, `Native`, `Level`), the two text
inputs render visibly taller than the `Level` `<select>`, even though the
shared CSS rule sets `min-height: 32px` on all three. The user wants them
to be the same height.

The mismatch comes from two interacting issues in
`tutor/static/app.css` (lines 31–42):

1. `font: inherit` pulls in the body's `line-height: 1.55`, then
   `font-size: 0.9rem` only overrides font-size. The inherited line-height
   makes the input's content box ~22px tall on its own.
2. `box-sizing` defaults to `content-box`, so `min-height: 32px` is the
   *content* box — total visual height becomes ~32 + 8 (padding) + 2
   (border) ≈ 42px for the `<input>`s. Native `<select>` rendering is more
   compact, so it lands closer to the declared 32px.

## Change

Edit the single shared rule in `tutor/static/app.css` at lines 31–42:

- Add `box-sizing: border-box;` so the declared height includes padding
  and border for both element types.
- Add `line-height: 1.2;` so the inherited 1.55 stops inflating the
  `<input>`'s intrinsic content height.
- Replace `min-height: 32px` with `height: 32px` to lock both elements to
  the same total height (no growth from line-height variations).

Resulting rule:

```css
.cfg-field input,
.cfg-field select {
    font: inherit;
    font-size: 0.9rem;
    line-height: 1.2;
    padding: 0.25rem 0.4rem;
    box-sizing: border-box;
    height: 32px;
    border: 1px solid #bbb;
    border-radius: 4px;
    background: transparent;
    color: inherit;
    min-width: 6rem;
}
```

No HTML or template changes are needed — `tutor/templates/partials/line.html`
already uses the same `.cfg-field` wrapper for all three controls
(lines 38–54), so this single CSS edit covers both the `Learning` /
`Native` inputs and the `Level` select.

## Files

- `tutor/static/app.css` — edit the `.cfg-field input, .cfg-field select`
  rule at lines 31–42.

## Verification

1. Start the dev server (`uv run --frozen` per project rules) and load a
   page that shows the per-line config row.
2. Visually confirm the `Learning`, `Native`, and `Level` fields are the
   same height; the row should sit flush.
3. Toggle dark mode (the dark-mode override at lines 319–320 only changes
   border-color, so heights should still match).
4. Confirm `intermediate` (the longest option label) still renders inside
   the select without clipping at the new 32px box-sizing: border-box
   height.
5. Run `make lint` to satisfy the project rule before declaring done.
