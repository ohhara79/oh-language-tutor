# Rename the page-fade slider from "Brightness" to "Opacity"

## Context

We just shipped a slider in the hamburger menu (commit `d64e49c`)
that fades the whole page by setting CSS `opacity` on `<body>`. It
was labeled **"Brightness"** because that's the word users associate
with display knobs — but `opacity` and `filter: brightness()` are
different things, and the user flagged that the label oversells what
the control actually does. **Opacity** matches the CSS property
exactly and is unambiguous, so we're renaming everywhere — UI label,
ARIA, CSS class / custom property, JS identifiers, and the persisted
localStorage key.

No behavior change. Slider range / direction / default stay the same
(30–100, higher = fully opaque = full ink).

## Decisions

- New visible label: **`Opacity  N%`** (`Opacity 100%` at default).
- New aria-label: **`Page opacity`**.
- CSS class prefix: **`.menu-opacity`** / **`#opacity-slider`** /
  **`#opacity-current`**.
- CSS custom property: **`--page-opacity`** on `<body>`.
- `CFG_DEFAULTS` key: **`pageOpacity`** (was `fontBrightness`).
- JS identifiers: `opacitySlider`, `opacityCurrent`, `applyOpacity`.
- Per-dataset persistence stays — under
  `tutor.audienceByDataset[datasetName].pageOpacity`. We do **not**
  add a migration for the old `fontBrightness` key: the feature
  shipped minutes ago and almost certainly has no users; carrying
  forward a single value isn't worth the code (and per CLAUDE.md
  "no backwards-compat shims").

## Files to modify

The three files touched by `d64e49c`:

1. `tutor/templates/index.html` — `.menu-brightness` block.
2. `tutor/static/app.css` — `.menu-brightness*` rules and the
   `body { opacity: var(--font-brightness, 1) }` line.
3. `tutor/static/app.js` — `CFG_DEFAULTS.fontBrightness` entry and
   the `brightnessSlider`/`applyBrightness` block.

## Rename map

Apply consistently across all three files:

| Old | New |
| --- | --- |
| `Brightness` (label text) | `Opacity` |
| `Font brightness` (aria-label) | `Page opacity` |
| `menu-brightness` (class) | `menu-opacity` |
| `menu-brightness-label` (class) | `menu-opacity-label` |
| `brightness-slider` (id) | `opacity-slider` |
| `brightness-current` (id) | `opacity-current` |
| `--font-brightness` (CSS var) | `--page-opacity` |
| `fontBrightness` (JS key, localStorage) | `pageOpacity` |
| `brightnessSlider` / `brightnessCurrent` (JS vars) | `opacitySlider` / `opacityCurrent` |
| `applyBrightness` (JS fn) | `applyOpacity` |

## Verification

1. `make lint` — must pass cleanly.
2. Start the app, open a dataset, open the hamburger menu — confirm
   the slider section now reads `Opacity 100%`.
3. Inspect element on the slider — `id="opacity-slider"`,
   `aria-label="Page opacity"`.
4. Drag the slider — page still fades live; label updates to e.g.
   `Opacity 70%`.
5. Reload — value persists (now under the `pageOpacity` key; old
   `fontBrightness` value, if any, is intentionally ignored).
6. `grep -nE 'brightness|fontBrightness|--font-brightness' tutor/`
   — should return zero hits across `templates/`, `static/app.css`,
   and `static/app.js` (only the freshly-renamed identifiers
   remain).
