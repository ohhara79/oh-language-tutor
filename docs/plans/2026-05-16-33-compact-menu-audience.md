# Compact the menu audience controls and drop the Stdin info line

## Context

After moving Learning / Native / Level into the header hamburger menu (commit `427740e`), the menu has more vertical content than fits comfortably on mobile. Two specific issues:

1. The shared `.cfg-field` rule (`tutor/static/app.css`) stacks the label above the input in a column flex; three audience fields therefore consume ~6 lines + gaps. The shared `min-width: 6rem` on inputs also prevents shrinking inside the narrow menu panel.
2. The "Stdin → `<dir>`" info row in `tutor/templates/index.html` is a passive, full-width text row plus its own separator — bulky for what it conveys.

Shrink the menu footprint by (a) collapsing each audience field to a single inline row `Label   [ input ]`, and (b) removing the Stdin info row and its dedicated separator.

## Approach

### `tutor/templates/index.html`

Remove the `{% if not is_writing_view %} <hr> <p class="menu-info">Stdin → …</p> {% endif %}` block from `#menu-panel`. The separator above the Jump block remains; the menu becomes: *Show only explained* → *Jump to …* → *Audience* → *Switch dataset*.

### `tutor/web.py`

Drop the `writing_dir=` and `is_writing_view=` kwargs from the `/tutor` `index()` render call — both were only consumed by the removed block. `ctx.writing_dir` itself stays on `WebContext` (still used by `make_dir_session`, the picker page render, and session resolution).

### `tutor/static/app.css`

Replace the `.menu-cfg` rules:

```css
.menu-cfg {
    padding: 0.5rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
}
.menu-cfg .cfg-field {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
}
.menu-cfg .cfg-label {
    flex: 0 0 4rem;
    font-size: 0.85rem;
}
.menu-cfg .cfg-field input,
.menu-cfg .cfg-field select {
    flex: 1;
    min-width: 0;
    width: auto;
}
```

`flex-direction: row` on `.cfg-field` overrides the shared column layout; `flex: 0 0 4rem` gives the label a fixed width; `min-width: 0` lets inputs shrink below the global 6rem floor on narrow viewports.

Delete the now-dead `.menu-info` rules.

## Files to modify

- `tutor/templates/index.html`
- `tutor/web.py`
- `tutor/static/app.css`

## Verification

1. `make lint` clean.
2. Run web mode, open `/tutor` on a 375px-wide viewport. Open hamburger menu.
3. Confirm order: *Show only explained* → *Jump to …* → **Learning / Native / Level** (each on a single inline row) → *Switch dataset*. No "Stdin → …" row.
4. Inputs do not overflow the menu panel; menu panel does not overflow the viewport.
5. Change a value, reload — value persists.
6. **Explain** still POSTs `source_language` / `target_language` / `level` correctly.
