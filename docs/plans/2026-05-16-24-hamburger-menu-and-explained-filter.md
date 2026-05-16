# Hamburger menu in raw sentence list view: switch dataset + filter to only-explained

## Context

The raw sentence list view (web mode, route `/tutor`, rendered by `tutor/templates/index.html`) currently exposes only a small "Switch dataset" link in the banner and offers no way to filter the stream. The user wants two new actions discoverable from a hamburger menu in the top-right of the header:

1. **Go back to tutor data selection menu** — same destination as today's "Switch dataset" link (`/`), but consolidated into the new menu.
2. **List only sentences with an explanation** (hide ones without) — a persistent toggle.

The filter mechanism will be a **client-side CSS toggle** (decided in planning): toggle a body class; CSS hides `.line:not(.has-explanation)`. This matches the project's "smallest change that works" preference and is sufficient because the `has-explanation` class is already authored on each line (`tutor/templates/partials/line.html:2`). The toggle's on/off state is persisted in `localStorage` using the existing `tutor.<key>` naming convention used by audience-config fields in `tutor/static/app.js:31-38`.

Pagination caveat (accepted): with the filter active, hidden lines still occupy the DOM, so the infinite-scroll sentinel may sit far down the page; the user may need to scroll a bit to load older pages. We're explicitly not adding a "Load more" button — keeping scope minimal.

## Approach

Three files change. All edits are in the web layer; no Python/server changes.

### 1. `tutor/templates/index.html` — restructure the header

Replace the `.view-banner` block (current lines 12–18) with a header that has a hamburger button on the right and a hidden dropdown panel. Preserve the "Viewing `<dir>` — new stdin lines stream into `<dir>`" status text (it's load-bearing context); only the "Switch dataset" link relocates into the new menu.

Sketch (final markup to be authored during implementation):

```html
<header>
  <div class="header-row">
    <h1>oh-language-tutor</h1>
    <button type="button" id="menu-btn" class="btn menu-btn"
            aria-haspopup="true" aria-expanded="false" aria-controls="menu-panel"
            aria-label="Menu">&#9776;</button>
  </div>
  <p class="view-banner">
    Viewing <code>{{ view_dir }}</code>{% if not is_writing_view %}
    <span class="view-banner-note">— new stdin lines stream into <code>{{ writing_dir }}</code></span>
    {% endif %}
  </p>
  <div id="menu-panel" class="menu-panel" hidden>
    <label class="menu-item menu-toggle">
      <input type="checkbox" id="filter-only-explained">
      <span>Show only explained</span>
    </label>
    <hr class="menu-sep">
    <a href="/" class="menu-item">Switch dataset</a>
  </div>
</header>
```

Notes:
- The hamburger reuses the existing `.btn` class so its size and focus styles match other buttons; a `.menu-btn` modifier strips the extra padding so it stays compact.
- The dropdown is positioned absolutely relative to `<header>`; `<header>` needs `position: relative` for that to work.
- Native `<hr>` for the separator — no extra elements needed.

### 2. `tutor/static/app.css` — menu styles + filter rule

Add three small CSS blocks (place near the existing `.switch-link` rule around line 29 and the `View states` section at line 324):

- **Header layout helpers:**
  - `header { position: relative; }` so the panel can be absolutely positioned.
  - `.header-row { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }` for title + hamburger row.
  - Remove or repurpose `.switch-link` (no longer used in the banner).
- **Hamburger button & panel:**
  - `.menu-btn { padding: 0.25rem 0.6rem; min-height: 36px; font-size: 1.2rem; line-height: 1; }` — keeps it visually compact while still tappable.
  - `.menu-panel { position: absolute; top: 100%; right: 1rem; z-index: 50; background: Canvas; border: 1px solid #bbb; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); min-width: 14rem; padding: 0.25rem 0; }` — uses the `Canvas` CSS system color so it adapts to light/dark mode (consistent with the existing `color-scheme: light dark` declaration at the top of the file).
  - `.menu-panel[hidden] { display: none; }` (explicit, since other rules in this file occasionally override `[hidden]`).
  - `.menu-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem; min-height: 44px; color: inherit; text-decoration: none; }` + a `.menu-item:hover { background: rgba(128,128,128,0.1); }` row, matching `.thread-list li.thread-item a` styling (lines 215–226).
  - `.menu-sep { border: 0; border-top: 1px solid #ddd; margin: 0.25rem 0; }`.
- **Filter rule** (add to the View states section around line 324):
  - `body.filter-only-explained .line:not(.has-explanation) { display: none; }`

### 3. `tutor/static/app.js` — open/close + persist filter

Insert one new IIFE-scoped block near the audience-config block (around line 31). It must NOT live inside the existing IIFE if it complicates ordering, but it can since it's the same file — just keep it logically grouped. Key behaviors:

```js
// Header menu: open/close + "show only explained" filter (persisted in localStorage).
const FILTER_KEY = 'tutor.onlyExplained';
const menuBtn = document.getElementById('menu-btn');
const menuPanel = document.getElementById('menu-panel');
const filterToggle = document.getElementById('filter-only-explained');

function setMenuOpen(open) {
    menuBtn.setAttribute('aria-expanded', String(open));
    menuPanel.hidden = !open;
}
menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    setMenuOpen(menuBtn.getAttribute('aria-expanded') !== 'true');
});
document.addEventListener('click', (e) => {
    if (!menuPanel.hidden && !menuPanel.contains(e.target) && e.target !== menuBtn) {
        setMenuOpen(false);
    }
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !menuPanel.hidden) setMenuOpen(false);
});

function applyFilter(on) {
    document.body.classList.toggle('filter-only-explained', on);
    filterToggle.checked = on;
}
applyFilter(localStorage.getItem(FILTER_KEY) === '1');
filterToggle.addEventListener('change', () => {
    const on = filterToggle.checked;
    localStorage.setItem(FILTER_KEY, on ? '1' : '0');
    applyFilter(on);
});
```

Why this shape:
- `aria-expanded` + `aria-controls` + `aria-haspopup` give the menu basic keyboard/screen-reader semantics with no library.
- Filter state is applied at startup *before* any user interaction so the initial paint already reflects the saved choice (no flash of unfiltered content; entries are server-rendered into `#stream-pane`).
- SSE-appended lines (`entry_appended` swap into `#stream-pane`, `index.html:25`) automatically inherit the filter because they carry `has-explanation` (or don't), and CSS handles visibility. No extra JS for new lines.
- Explanation streaming sets `has-explanation` during streaming (`partials/line.html:2`), so streaming lines remain visible while the filter is on.

## Files to modify

- `tutor/templates/index.html` — replace `.view-banner` block (lines 12–18) with header-row + menu-panel structure.
- `tutor/static/app.css` — add header/menu styles near line 29, and the filter rule near line 324; drop the unused `.switch-link` rule.
- `tutor/static/app.js` — add menu open/close + filter persistence block near line 31.

No changes to `tutor/web.py`, no changes to `tutor/templates/partials/line.html`, no changes to server-side pagination.

## Verification

Manual (no test framework configured — see `docs/rules/project-structure.md`):

1. `make lint` clean (basedpyright + ruff).
2. Run web mode: `uv run --frozen python main.py --web ...` (use whichever invocation the user normally uses; see `README.md`).
3. Visit `/`, pick a dataset, land on `/tutor`. Confirm hamburger button visible top-right of header; the banner status text still reads `Viewing <dir>`.
4. Click hamburger → panel opens with checkbox + "Switch dataset" link.
5. Click outside the panel → closes. Press Esc → closes. Click hamburger again → toggles closed.
6. Toggle "Show only explained" → lines without an explanation disappear; lines with `has-explanation` (blue left border) remain. Reload the page → toggle state restored, filter still applied on initial paint.
7. Toggle off → all lines visible again; reload → off state persisted.
8. With filter on, pipe a new line into stdin → it appears appended only if it ends up explained (or while streaming). Click "Explain" on a still-visible (already-explained) line → streaming line stays visible.
9. Click "Switch dataset" in the menu → returns to `/`.
10. Open a thread (`Ask` button) → thread-detail view still works; existing `#thread-topbar` Back button unchanged. Hamburger remains accessible from thread view (harmless; filter has no visible effect there since `#stream-pane` is hidden).
11. Plan file for the project: at implementation time, also create `docs/plans/2026-05-16-24-hamburger-menu-and-explained-filter.md` per `docs/rules/plans.md` (the next sequence number for today is `-24-`, after `2026-05-16-23-test-coverage-boost.md`).
