# Add font brightness slider to hamburger menu

## Context

The hamburger menu already exposes a few reading-experience controls
("Show only explained", "Jump to Nth sentence", language/level config).
A brightness slider would let the user dim the page while reading in a
dark room (or at night) without leaving the site or relying on
OS-level brightness. The slider applies `opacity` to the whole page,
persists per-dataset like the other menu settings, and follows the
same vanilla-JS + plain-CSS patterns already in use — no new
dependencies, no framework, no build step.

## Decisions (from clarifying Qs)

- **Scope:** entire page — `opacity` set on `<body>` (or `:root`). The
  menu panel itself dims while the user slides, which is fine — it
  gives live feedback, and the menu remains readable down to 30%.
- **CSS technique:** `opacity` (uniform in light and dark mode).
- **Persistence:** per-dataset, reusing the existing
  `tutor.audienceByDataset[datasetName].fontBrightness` slot and the
  `cfgGet`/`cfgSet` helpers.

## Files to modify

1. `tutor/templates/index.html` — add the slider markup inside
   `#menu-panel`.
2. `tutor/static/app.css` — style the new `.menu-brightness` block and
   wire a `--font-brightness` custom property to `body { opacity: … }`.
3. `tutor/static/app.js` — add `fontBrightness` to `CFG_DEFAULTS`,
   hydrate the slider on load, apply the value, and write back on
   `input`.

No backend changes — the value never needs to reach the server.

## Implementation

### 1. HTML (`tutor/templates/index.html`)

Insert a new section between the existing "Jump to" block and the
`.menu-cfg` config block (so it lives roughly where line 35 currently
has its `<hr class="menu-sep">`):

```html
<hr class="menu-sep">
<div class="menu-brightness">
  <div class="menu-brightness-label">
    Brightness <span id="brightness-current">100</span>%
  </div>
  <input type="range" id="brightness-slider"
         min="30" max="100" step="5" value="100"
         aria-label="Font brightness">
</div>
```

Stored value is an integer percent (30–100) so it matches the existing
"strings of digits" convention of `CFG_DEFAULTS` (e.g. `onlyExplained:
'0'`).

### 2. CSS (`tutor/static/app.css`)

Reuse the `.menu-jump` layout (it already has the right padding /
flex / gap):

```css
.menu-brightness {
    padding: 0.375rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}
.menu-brightness-label { font-size: 0.9rem; }
#brightness-slider { width: 100%; min-height: 32px; }

body { opacity: var(--font-brightness, 1); }
```

Setting the custom property on `<body>` (from JS) keeps all state in
one place and avoids hand-rolling inline style strings.

### 3. JS (`tutor/static/app.js`)

a. Add a key to `CFG_DEFAULTS` (around line 28):

```js
fontBrightness: '100',
```

b. After the existing jump-slider block (around line 184), add:

```js
const brightnessSlider = document.getElementById('brightness-slider');
const brightnessCurrent = document.getElementById('brightness-current');
function applyBrightness(pct) {
    const v = Math.max(30, Math.min(100, Number(pct) || 100));
    body.style.setProperty('--font-brightness', String(v / 100));
    brightnessCurrent.textContent = String(v);
    brightnessSlider.value = String(v);
}
applyBrightness(cfgGet('fontBrightness'));
brightnessSlider.addEventListener('input', () => {
    const v = brightnessSlider.value;
    cfgSet('fontBrightness', v);
    applyBrightness(v);
});
```

This mirrors the `onlyExplained` filter pattern (apply on load → wire
listener → persist via `cfgSet`) and the jump slider's input-event
shape. Clamping in `applyBrightness` guards against bad stored values
from older sessions.

## Verification

1. `make lint` — no Python changes, but run anyway per the repo rule.
2. Start the app (the `run` skill, or whatever launches the FastAPI
   server locally) and open a dataset.
3. Open the hamburger menu — confirm the new "Brightness 100%" label
   and slider appear between "Jump to" and the language config block.
4. Drag the slider — the whole page should dim live; the percent
   label should update; the slider thumb position should remain
   visible.
5. Close and reopen the menu — value persists; page stays dimmed.
6. Reload the page — value still persists.
7. Switch to a different dataset (via the home page) — that dataset
   shows its own brightness (default 100% if never set), proving
   per-dataset isolation.
8. Toggle the OS to dark mode — slider still dims uniformly (opacity
   is mode-agnostic).
9. Set brightness to 30%, close menu, refresh — verify the page loads
   already dim (no flash of full-brightness before JS runs is
   acceptable; the script tag is at the bottom of `<body>`, so a
   brief flash is expected and matches how `onlyExplained` works
   today).
