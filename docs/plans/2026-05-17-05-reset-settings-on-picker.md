# Move "Reset settings" to a hamburger on the dataset picker

## Context

`Reset settings` currently lives in the main view's hamburger menu
(`tutor/templates/index.html`, JS handler in `tutor/static/app.js`).
But the action wipes *global* state — every `tutor.*` localStorage key
plus the `view_state_dir` cookie — and on success the page reloads
straight to the dataset picker. So conceptually it's a picker-level
action, not a per-dataset action. Moving it makes the main hamburger
purely about per-dataset settings (filter, jump, audience) and gives
the picker the destructive escape hatch where it naturally belongs.

The user also wants a hamburger menu on the picker view at all (it
currently has none — just an `<h1>` and a list of datasets).

## Approach

### 1. Picker template — `tutor/templates/picker.html`

Replace the bare `<header><h1>...</h1></header>` with the same
`.header-row` + menu-button + `#menu-panel` shape used on the index
page, containing one item:

```html
<header>
  <div class="header-row">
    <h1>oh-language-tutor</h1>
    <button type="button" id="menu-btn" class="btn menu-btn"
            aria-haspopup="true" aria-expanded="false" aria-controls="menu-panel"
            aria-label="Menu">&#9776;</button>
  </div>
  <div id="menu-panel" class="menu-panel" hidden>
    <button type="button" id="reset-settings" class="menu-item">Reset settings</button>
  </div>
</header>
```

Add a script include just before `</body>`:
`<script src="/static/picker.js?v={{ version }}"></script>`.

All existing CSS rules (`.header-row`, `.menu-btn`, `.menu-panel`,
`.menu-item`) already live in `tutor/static/app.css` which the picker
already loads — no CSS additions needed.

### 2. New file — `tutor/static/picker.js`

A minimal IIFE that wires the same menu open/close behavior and the
same Reset-settings click handler that lives in `app.js`. We can't
just include `app.js` on the picker: it null-derefs `.menu-cfg`,
`#filter-only-explained`, `#stream-pane`, etc. The duplication is ~25
small lines and self-contained; extracting a shared module is
over-engineering at this size.

Behavior identical to today's `app.js` handler at the reset block
(currently after the filter-toggle listener) and the menu open/close
block (currently around `setMenuOpen`/document click/Escape
listeners):

- Toggle menu open/closed on `#menu-btn` click
- Close on outside click and Escape
- On Reset click: native `confirm()` → wipe every `tutor.*`
  localStorage key → clear `view_state_dir` cookie (`Max-Age=0;
  path=/`) → `location.reload()`

### 3. Index template — `tutor/templates/index.html`

Remove the trailing `<hr class="menu-sep">` and `<button
id="reset-settings">` rows from `#menu-panel` (the last two lines
before `</div>`).

### 4. `tutor/static/app.js`

Delete the Reset-settings comment + click handler block (between the
filter-toggle listener and the "Hamburger jump to Nth sentence
slider" section). Nothing else in `app.js` references
`#reset-settings`.

### 5. CSS containing-block fix — `tutor/static/app.css`

The menu panel is `position: absolute; top: 100%; right: 1rem;`. On
index it positions correctly because `body:not(.view-picker) header`
is `position: sticky`, which establishes a containing block. The
picker header is static, so the panel would resolve against the
viewport and land below the page. Fix by adding `position: relative`
to the base `header` rule (line 11-15). This is a no-op on index
(sticky already provides the containing block) and corrects the
picker.

## Files to touch

- `tutor/templates/picker.html` — expand the header, add menu panel +
  script tag.
- `tutor/static/picker.js` — new file, ~30 lines.
- `tutor/templates/index.html` — drop the trailing separator + Reset
  button rows.
- `tutor/static/app.js` — drop the Reset-settings click handler block.
- `tutor/static/app.css` — add `position: relative` to the base
  `header` rule.

No backend changes.

## Verification

1. `make lint` passes.
2. Manual browser checks:
   - Navigate to `/?picker=1`. Confirm a hamburger appears top-right
     on the picker page, with `Reset settings` as its only item.
     Panel drops down from below the button (not below the page).
   - Click `Reset settings` on the picker → confirm prompt → accept
     → localStorage `tutor.*` keys cleared, `view_state_dir` cookie
     cleared, page reloads onto picker. DevTools confirms the
     cleared state.
   - Click `Reset settings` on the picker → cancel → nothing happens.
   - Open `/tutor` (or pick a dataset). Confirm the index hamburger
     no longer shows `Reset settings` or the separator above it; the
     remaining items (Show only explained, Jump slider, audience
     config) all still work.
   - Outside-click and Escape close the picker menu.
   - Dark mode + ellipsized long titles: header still looks right on
     both pages.
3. Confirm no console errors on the picker page (the script-only-on-
   picker setup avoids the previous null-deref risk from `app.js`).
