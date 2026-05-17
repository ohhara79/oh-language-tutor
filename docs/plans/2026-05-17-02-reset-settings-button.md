# Add "Reset settings" to the hamburger menu

## Context

The hamburger menu now persists audience settings (Learning, Native,
Level, Show only explained) per-dataset under `tutor.audienceByDataset`,
plus scroll position per-dataset under `tutor.lastAnchors`, plus legacy
flat keys (`tutor.sourceLanguage`, `tutor.targetLanguage`, `tutor.level`,
`tutor.onlyExplained`) kept as a fallback. The currently-viewed dataset
is tracked in the `view_state_dir` cookie (set by `POST
/commands/open_state_dir`, 365-day Max-Age).

There's no single way for a user to start over: they'd have to open
devtools, clear localStorage, and delete the cookie. A "Reset settings"
control inside the existing menu fixes that.

## Approach

Pure client-side reset — no new backend endpoint, since all the state
lives in localStorage and a cookie that JS can clear directly.

### UI

Add the button at the bottom of `#menu-panel` in
`tutor/templates/index.html`, after the audience config block (after
line 55), preceded by a `<hr class="menu-sep">`:

```html
<hr class="menu-sep">
<button type="button" id="reset-settings" class="menu-item">Reset settings</button>
```

Placement at the bottom matches the pattern of putting less-common /
heavier-weight actions last. Reuses the existing `.menu-item` class so
no CSS work is needed.

### Behavior (`tutor/static/app.js`)

Wire a click handler near the other menu code (around the existing
`filterToggle` listener at lines ~127-131):

1. Show a native `confirm()` with a message naming what's wiped — e.g.
   "Reset all settings? This clears audience choices, scroll position,
   and the current dataset selection across all datasets."
2. On confirm:
   - Remove every `localStorage` key that starts with `tutor.` (covers
     `tutor.audienceByDataset`, `tutor.lastAnchors`, the four legacy
     flat keys, and any future `tutor.*` key without needing
     maintenance):
     ```js
     Object.keys(localStorage)
         .filter(k => k.startsWith('tutor.'))
         .forEach(k => localStorage.removeItem(k));
     ```
   - Clear the `view_state_dir` cookie by setting it with `Max-Age=0`
     and `path=/` (the same path the server sets):
     ```js
     document.cookie = 'view_state_dir=; Max-Age=0; path=/';
     ```
   - `location.reload()`. Because the cookie is gone, the server falls
     through to the dataset picker, giving the user a clean entry
     point.

### Why no backend endpoint

`/commands/clear_explanation` uses an endpoint because the state lives
in server-side files. Here every piece of state is browser-side
(localStorage + a JS-readable cookie with `httponly=False` at
`tutor/web.py:364-370`), so a round-trip would only add latency.

## Files to touch

- `tutor/templates/index.html` — insert the button + separator after
  line 55 inside `#menu-panel`.
- `tutor/static/app.js` — add the click handler. Natural spot is right
  after the existing filter-toggle wiring (~line 131), grouping
  menu-action wiring together.

## Verification

1. `make lint` passes.
2. Manual browser check:
   - Open dataset A; set Learning=English / Native=Korean / Level=intermediate
     / "Show only explained"=on; scroll to a specific sentence.
   - Switch to dataset B; change its settings to something different.
   - Open menu → click "Reset settings" → cancel the confirm; verify
     nothing changed (settings, scroll, dataset still intact).
   - Open menu → click "Reset settings" → accept the confirm.
   - Page reloads and lands on the dataset picker (cookie cleared).
   - DevTools → Application → Local Storage: every `tutor.*` key is
     gone. Cookies: `view_state_dir` is gone.
   - Pick a dataset again; verify defaults apply (English/Korean/
     intermediate/Show-only-explained off) and scroll lands on the
     newest sentence (the no-saved-anchor fallback at
     `tutor/static/app.js:374-376`).
3. Edge: clicking Reset when no `tutor.*` keys or cookie exist (i.e.
   already-clean state) should still reload to the picker without
   error.
