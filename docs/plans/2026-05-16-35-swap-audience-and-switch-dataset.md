# Swap Switch dataset and the audience block in the hamburger menu

## Context

The audience block (Learning / Native / Level) is the bulkiest item in the hamburger menu and is touched less often than *Switch dataset*. Pushing the audience block to the very bottom keeps the short, frequently-used items near the hamburger button.

Previous order:

1. Show only explained
2. Jump to N / N
3. Audience
4. Switch dataset

New order:

1. Show only explained
2. Jump to N / N
3. Switch dataset
4. Audience

## Approach

One file: `tutor/templates/index.html`. Swap the `<div class="menu-cfg">…</div>` block and the `<a href="/" class="menu-item">Switch dataset</a>` line inside `#menu-panel`. The `<hr class="menu-sep">` separators stay where they are — both blocks already have a separator above them.

No CSS, JS, or server changes. `.menu-cfg` styling and the `cfgHydrateMenu()` / `htmx:configRequest` plumbing in `tutor/static/app.js` are position-independent.

## Files to modify

- `tutor/templates/index.html`

## Verification

1. `make lint` clean.
2. Reload `/tutor`, click the hamburger.
3. Order is: *Show only explained* → *Jump to …* → *Switch dataset* → *Learning / Native / Level*.
4. Audience controls still hydrate from / persist to `localStorage`; **Explain** still posts `source_language` / `target_language` / `level`.
