# Add − / + step buttons to opacity and font-size sliders

## Context

The hamburger menu's Opacity slider (`2026-05-23-01`) and Font Size slider
(`2026-05-23-02`) both use `<input type="range">`. On touch devices and
small screens it is hard to land on a specific value by dragging the
thumb. The user wants flanking **−** / **+** buttons that nudge each
value in 10-percentage-point steps so an exact target is one tap away.

## Decisions

- Layout: `[−] [slider] [+]` in a single flex row directly under the
  existing `Opacity N%` / `Font Size N%` label. Buttons sit *close* to
  the slider rather than at the edges of the menu panel so they read as
  belonging to that control.
- Step size: **10** for both sliders, regardless of the slider's own
  `step` attribute (opacity uses `step=5`, font size uses `step=10`).
  The user's request was explicitly "10% step."
- Clamping: each step clamps to the slider's own `min`/`max`
  (opacity `[30, 100]`, font size `[50, 300]`). At the boundary the
  corresponding button becomes `disabled` so users see they cannot push
  further.
- Persistence: identical path to slider drag — `cfgSet(<key>, v)` +
  `apply<Slider>(v)`. The stepper is purely a different input affordance
  for the same state.
- CSS: one shared `.slider-row` (flex container) + `.slider-step`
  (button) rule used by both sliders. The slider element itself becomes
  `flex: 1; min-width: 0` so it absorbs the remaining width.
- Markup uses `&minus;` (U+2212) for the minus glyph rather than a hyphen
  so it visually matches `+` weight; aria-labels spell out
  "Decrease/Increase … by 10%" for screen readers.

## Files to modify

1. `tutor/templates/index.html` — wrap each of `#opacity-slider` and
   `#fontsize-slider` in `<div class="slider-row">` with sibling
   `<button class="slider-step" id="opacity-minus|plus">` and
   `<button class="slider-step" id="fontsize-minus|plus">`.
2. `tutor/static/app.css`:
   - Change `#opacity-slider` and `#fontsize-slider` from
     `width: 100%` to `flex: 1; min-width: 0` so they share the row.
   - Add `.slider-row` (flex, `gap: 0.375rem`, vertically centered) and
     `.slider-step` (≥32×32, neutral border + bg, `:active` + `:disabled`
     states).
3. `tutor/static/app.js`:
   - Look up the four new button elements next to the existing slider
     handles.
   - Add `stepOpacity(delta)` / `stepFontSize(delta)` that read the
     current slider value, add `delta`, clamp to the slider's range, then
     route through `cfgSet` + `apply*` (same code path as drag).
   - Inside `applyOpacity` / `applyFontSize`, toggle each button's
     `disabled` based on whether the clamped value is at the boundary.
   - Wire `click` listeners: `±10` per click.

## Why a shared `apply*` path

`applyOpacity` and `applyFontSize` already (a) clamp, (b) update the
display span, (c) sync the slider value, and now (d) toggle button
disabled state. Routing every input source through the same function
keeps the slider, the buttons, and the persisted config in lockstep with
no drift.

## Why disable at boundary instead of silently no-op'ing

A button that does nothing on click is confusing on touch — the user
cannot tell whether the tap registered. `disabled` makes the limit
discoverable without a toast or animation.

## Verification

1. `make lint` — must pass (no Python touched, but the lint target also
   covers formatting/check).
2. Open the hamburger menu — confirm `[−] [slider] [+]` is laid out on
   one row directly under each of `Opacity` and `Font Size`, with the
   slider absorbing the remaining width.
3. Click `+` on Opacity until the value reaches `100` — the `+` button
   becomes disabled; the slider thumb sits at max. Click `−` once — `+`
   re-enables, value drops to `90`.
4. Click `+` / `−` on Font Size — value steps by 10 each click, clamped
   to `[50, 300]`. Buttons disable at the respective boundary.
5. Drag the slider to mid-range, then click a step button — value moves
   by exactly 10 from the dragged position (not snapped to a multiple
   of 10), proving the stepper is delta-based.
6. Reload — last value persists under the existing
   `tutor.audienceByDataset[<dir>].pageOpacity` / `.fontSize` keys; no
   new config key was introduced.
