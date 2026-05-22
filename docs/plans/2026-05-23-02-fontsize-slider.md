# Add Font Size slider to hamburger menu

## Context

The hamburger menu already exposes an Opacity slider (commit `d64e49c` /
renamed in `b477493`) that scales a single CSS custom property and persists
the value per-dataset via `cfgGet` / `cfgSet`. The user wants a sibling
**Font Size** slider with a 50%–300% range so reading text can be enlarged
or shrunk without using browser zoom (which would also rescale the chrome
and break sticky-header layout).

## Decisions

- New visible label: **`Font Size  N%`** (`Font Size 100%` at default).
- New aria-label: **`Content font size`**.
- Range / step: `min=50  max=300  step=10  value=100`.
- CSS class prefix: **`.menu-fontsize`** / **`#fontsize-slider`** /
  **`#fontsize-current`**.
- CSS custom property: **`--content-scale`** on `:root` (set via JS on
  `document.documentElement`). Defaults to `1` via `var(..., 1)` fallback
  so no explicit `:root` declaration is needed.
- `CFG_DEFAULTS` key: **`fontSize`** (`'100'`).
- JS identifiers: `fontSizeSlider`, `fontSizeCurrent`, `applyFontSize`.
- Per-dataset persistence under
  `tutor.audienceByDataset[datasetName].fontSize`, same shape as
  `pageOpacity`.
- **Scope: content only.** Only the line list and the thread view scale.
  Header / hamburger button / menu panel / config inputs stay at their
  current size so the menu remains usable at 300%.

## Files to modify

1. `tutor/templates/index.html` — insert a `.menu-fontsize` block (preceded
   by `<hr class="menu-sep">`) immediately after the `.menu-opacity` block.
2. `tutor/static/app.css`:
   - Add `.menu-fontsize` / `.menu-fontsize-label` / `#fontsize-slider`
     rules cloned from the opacity ones.
   - Add `.thread-conversation { font-size: calc(1rem * var(--content-scale, 1)); }`
     so `.msg` text inside the thread (which has no explicit font-size)
     scales via inheritance.
   - Change the three content-side `font-size: 1.5rem` declarations to
     multiply by `var(--content-scale, 1)`: `.raw-toggle`,
     `.explanation-body`, `.anchor-raw`.
3. `tutor/static/app.js`:
   - Add `fontSize: '100'` to `CFG_DEFAULTS`.
   - After the opacity slider block, add an analogous `applyFontSize(pct)`
     that clamps to `[50, 300]`, sets `--content-scale` on
     `document.documentElement`, updates `#fontsize-current`, and syncs the
     slider value. Wire `input` to `cfgSet('fontSize', v)` + `applyFontSize`,
     and hydrate once on load via `applyFontSize(cfgGet('fontSize'))`.

## Why scale via a CSS variable (not per-element `style.fontSize`)

A single `--content-scale` keeps the live DOM untouched: lines streamed in
later via SSE (`sse-swap="entry_appended"`) automatically inherit the
current scale without any post-swap JS. This matches how `--page-opacity`
already works.

## Why only specific declarations (not a container `font-size`)

Because content-side font-sizes in `app.css` are declared in `rem`, raising
the container's `font-size` does not cascade into the children — they
re-resolve against `:root`. So we multiply each of the targeted content
declarations explicitly. `.thread-conversation` is the one exception: its
`.msg` children have no explicit `font-size` and do inherit, so setting it
on the container is the right hook there.

## Verification

1. `make lint` — must pass cleanly (template + static assets only, no
   Python).
2. Launch the app and open a dataset; open the hamburger menu — confirm a
   new `Font Size 100%` row sits between Opacity and the Learning / Native /
   Level config block.
3. Drag the slider — line text (`.raw-toggle`, `.explanation-body`) and
   thread text (`.anchor-raw`, `.msg`) resize live; header / menu chrome
   stay put.
4. Reload — value persists under
   `tutor.audienceByDataset[<dir>].fontSize`.
5. Stream a new line (or wait for SSE append) at a non-100% setting — the
   new line renders at the current scale immediately, with no post-swap JS.
6. Switch to a different state dir via the picker — the new dataset starts
   at its own value (100% by default), confirming per-dataset persistence.
