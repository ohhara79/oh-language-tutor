# Remove lazy-loading; add "Jump to Nth raw sentence" slider

## Context

The list view currently loads only the last 500 entries on page open and lazy-loads older entries when the user scrolls to the top (HTMX `intersect once` sentinel hitting `GET /partials/older`). The user finds this inconvenient when there are many sentences — scrolling far back is slow because each scroll-to-top triggers a network round-trip.

Goal: load **all** raw sentences up front, drop the auto-load-on-scroll machinery entirely, and add a dataset-wide jump control in the hamburger menu (slider + total count) so the user can reach any sentence directly.

User-confirmed design points:
- Slider scrolls **live as the user drags** (`input` event).
- Index #1 = oldest, #N = newest (array order).
- Action on jump = `scrollIntoView` only (no highlight, no expansion).

## Approach

### 1. Backend: load everything, drop the `/partials/older` endpoint

`tutor/web.py`:
- In the `GET /tutor` handler (`index`, currently at line 366): replace `session.tutor_store.load_tail(_STREAM_PAGE_N)` with `session.tutor_store.load()`. Drop the `has_more`, `oldest_id`, and `page_n` template variables — they are no longer used.
- Delete the entire `GET /partials/older` route (currently lines 387–405).
- Delete the `_STREAM_PAGE_N = 500` constant (line 53) once it has no remaining callers.

`tutor/tutor_store.py`:
- Delete `load_tail` (lines 153–159) and `load_before` (lines 161–172). These have no other callers (verified by exploration); `load()` plus `index_of` remain.

`tutor/templates/partials/older_lines.html`:
- Delete the file.

### 2. Template: render full list; remove sentinel; add slider menu item

`tutor/templates/index.html`:
- Remove the `#load-older-indicator` div (line 39) and the `{% if has_more %}` sentinel block (lines 40–47). The `{% for entry in entries %}` loop stays and now renders every entry.
- Inside `#menu-panel`, insert a new menu section above the "Switch dataset" link, gated on `entries|length > 0`:

  ```html
  <hr class="menu-sep">
  <div class="menu-jump">
    <div class="menu-jump-label">
      Jump to <span id="jump-current">{{ entries|length }}</span>
      / <span id="jump-total">{{ entries|length }}</span>
    </div>
    <input type="range" id="jump-slider"
           min="1" max="{{ entries|length }}" value="{{ entries|length }}"
           aria-label="Jump to sentence">
  </div>
  ```

  Initial value = total count (newest sentence) so the slider position matches the page's natural bottom-anchored view on load.

### 3. JS: drop the scroll-position fixer; wire up the slider

`tutor/static/app.js`:
- Delete the load-older scroll-position fixer (the `_loadOlderBefore` block at lines 310–328).
- Add slider wiring inside the existing menu-setup section (around line 111, after the filter toggle). Roughly:

  ```js
  const jumpSlider = document.getElementById('jump-slider');
  const jumpCurrent = document.getElementById('jump-current');
  const jumpTotal = document.getElementById('jump-total');
  const streamPane = document.getElementById('stream-pane');

  function jumpRefreshTotal() {
      if (!jumpSlider) return;
      const lines = streamPane.querySelectorAll('.line');
      const n = lines.length;
      jumpTotal.textContent = String(n);
      jumpSlider.max = String(Math.max(n, 1));
      jumpSlider.disabled = n === 0;
      if (Number(jumpSlider.value) > n) jumpSlider.value = String(n);
  }

  function jumpScrollTo(index) {
      const lines = streamPane.querySelectorAll('.line');
      if (!lines.length) return;
      const i = Math.min(Math.max(index, 1), lines.length) - 1;
      lines[i].scrollIntoView({block: 'start'});
  }

  if (jumpSlider) {
      jumpSlider.addEventListener('input', () => {
          const v = Number(jumpSlider.value);
          jumpCurrent.textContent = String(v);
          jumpScrollTo(v);
      });
  }
  ```

- Have `jumpRefreshTotal()` run once on init and again whenever entries are appended. The existing MutationObserver on `#stream-pane` (line 298) is the natural hook — call `jumpRefreshTotal()` from inside its callback so the total updates as new SSE entries arrive. Also call it once after `distributeThreads()` on initial load.

Behavior note: live `input` scrolling uses default (non-smooth) `scrollIntoView` so each tick is instant; smooth scrolling would lag behind the drag.

### 4. CSS: drop the indicator style; style the slider row

`tutor/static/app.css`:
- Remove the `#load-older-indicator` rule (lines 169–176).
- Add minimal styling for the new menu section. The slider needs comfortable touch sizing and the label needs to sit inside the existing 14rem-min menu panel:

  ```css
  .menu-jump { padding: 0.5rem 0.75rem; display: flex; flex-direction: column; gap: 0.4rem; }
  .menu-jump-label { font-size: 0.9rem; }
  #jump-slider { width: 100%; min-height: 32px; }
  ```

## Files to modify

- `tutor/web.py` — drop `_STREAM_PAGE_N`, switch `index` to `load()`, delete `/partials/older` route.
- `tutor/tutor_store.py` — delete `load_tail` and `load_before`.
- `tutor/templates/index.html` — remove sentinel + indicator; add jump-slider section to menu panel.
- `tutor/templates/partials/older_lines.html` — delete.
- `tutor/static/app.js` — delete `_loadOlderBefore` fixer; add slider wiring; refresh total inside existing stream-pane MutationObserver.
- `tutor/static/app.css` — remove `#load-older-indicator` rule; add `.menu-jump` styling.

## Verification

1. Ensure a dataset with many (≥600) raw sentences exists, or seed one. Start the server: `uv run --frozen <project entrypoint>` (per `CLAUDE.md`).
2. Open `/tutor` in a browser:
   - View source / DevTools: confirm **all** entries are rendered (no `load-older-sentinel` in the DOM).
   - Scroll to the very top: no network request fires, no indicator appears.
3. Open the hamburger menu:
   - Confirm the "Jump to N / N" label and slider appear above "Switch dataset".
   - Drag the slider: the label updates live and the page scrolls to the corresponding line in real time.
   - Drag to `1`: the oldest entry is at the top of the viewport. Drag to max: the newest entry is at the top of the viewport.
4. With the page open, append a new entry (via the writing flow / stdin → writing_dir). After the SSE swap, reopen the menu and confirm the slider's max and total have incremented.
5. Switch to a dataset with zero entries: slider is disabled, total reads `0`, no JS errors in console.
6. Run `make lint` and `make format` per `CLAUDE.md`. Confirm `basedpyright` is clean.
