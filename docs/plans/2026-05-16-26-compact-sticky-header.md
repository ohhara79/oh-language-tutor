# Compact the sticky header to a single dataset-name + hamburger row

## Context

The previous change made the sentence-list header sticky so the hamburger menu stays reachable on mobile. On small viewports with long dataset paths, however, the header now occupies 50–70% of the visible viewport. Two culprits:

1. `<h1>oh-language-tutor</h1>` on its own row (~2rem) — redundant with the browser tab/window title.
2. The `<p class="view-banner">` ("Viewing `<dir>` — new stdin lines stream into `<writing_dir>`") uses `flex-wrap: wrap`, so with a non-writing view + long dir names it wraps to 3–5 lines.

Fix: collapse the sticky portion to a single row containing only the current dataset name (left, truncated with ellipsis) and the hamburger (right). The "stdin streams into <writing_dir>" note — only relevant when viewing a non-writing dataset — moves into the menu panel as a static info line, gated on `is_writing_view` being false. Target sticky height: ~2.5rem.

## Approach

Two files change. No JS, no server changes.

### 1. `tutor/templates/index.html` — slim the `<header>`

New structure:

```html
<header>
  <div class="header-row">
    <span class="view-dir-label" title="{{ view_dir }}">{{ view_dir }}</span>
    <button type="button" id="menu-btn" class="btn menu-btn"
            aria-haspopup="true" aria-expanded="false" aria-controls="menu-panel"
            aria-label="Menu">&#9776;</button>
  </div>
  <div id="menu-panel" class="menu-panel" hidden>
    <label class="menu-item menu-toggle">
      <input type="checkbox" id="filter-only-explained">
      <span>Show only explained</span>
    </label>
    {% if not is_writing_view %}
    <hr class="menu-sep">
    <p class="menu-info">Stdin &rarr; <code>{{ writing_dir }}</code></p>
    {% endif %}
    <hr class="menu-sep">
    <a href="/" class="menu-item">Switch dataset</a>
  </div>
</header>
```

Removed elements: `<h1>oh-language-tutor</h1>` and the entire `<p class="view-banner">` block. The dataset name (`view_dir`) becomes the only header content alongside the hamburger; the writing-dir note relocates into the menu panel and only renders when applicable (matches today's `{% if not is_writing_view %}` conditional).

The `title="{{ view_dir }}"` attribute on the label provides the full name on desktop hover when truncated. Mobile users can confirm the dataset by tapping "Switch dataset" (the picker lists names in full).

### 2. `tutor/static/app.css` — drop obsolete rules, add the new ones

- **Removed** (no longer used): `header h1 { ... }`, the entire `.view-banner` rule and `.view-banner code` / `.view-banner-note` selectors.
- **Tightened** `.header-row`: dropped `margin-bottom: 0.25rem` (no second row to gap from).
- **Added** `.view-dir-label`:
  ```css
  .view-dir-label {
      font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
      font-size: 1rem;
      font-weight: 600;
      min-width: 0;             /* allow flex item to shrink below content width */
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
  }
  ```
  `min-width: 0` + `flex: 1` is the standard recipe to let a flex item truncate with ellipsis instead of growing the row.
- **Added** `.menu-info` for the static informational line inside the menu panel:
  ```css
  .menu-info {
      margin: 0;
      padding: 0.5rem 0.75rem;
      font-size: 0.85rem;
      color: #888;
  }
  .menu-info code { font-size: 0.85rem; }
  ```
  Smaller than `.menu-item`, no hover state — visually distinguishes info from clickable actions.

## Files modified

- `tutor/templates/index.html` — header body restructured per above.
- `tutor/static/app.css` — removed `header h1`, `.view-banner`, `.view-banner code`, `.view-banner-note`; trimmed `.header-row`; added `.view-dir-label` and `.menu-info`.

No changes to `tutor/static/app.js` (menu IDs and the filter-toggle checkbox keep the same IDs).
No changes to `tutor/web.py` (template still receives `view_dir`, `writing_dir`, `is_writing_view`).

## Verification

Manual (no test framework configured):

1. `make lint` clean.
2. Run web mode, open `/tutor` on a writing-view dataset. Confirm sticky header is a single row: dataset name (truncated with `…` if long) on the left, hamburger on the right. Open menu → "Show only explained" + "Switch dataset" present; no info line shown.
3. Open `/tutor` on a non-writing-view dataset (i.e., choose a different dataset in the picker, leaving stdin pointed at the original). Confirm header still single-row, and the menu now shows the `Stdin → <writing_dir>` info line between the filter toggle and the "Switch dataset" link.
4. With a very long dataset name (or zoom in DevTools), confirm the name truncates with `…` instead of wrapping or pushing the hamburger off-screen. Hover the label on desktop → full name shown via `title` tooltip.
5. Scroll mid-stream → the single-row header stays pinned at the top and now occupies a small fraction of the viewport. Tap hamburger → dropdown still drops correctly from the now-shorter header.
6. Toggle "Show only explained" → filter still works, state still persists across reloads (no JS changed).
7. Click "Switch dataset" → returns to picker `/`.
8. Enter thread view via "Ask" → header stays pinned and compact; `#thread-topbar` Back button works as before.
9. Dark mode: confirm `.view-dir-label` reads cleanly (inherits color; monospace font); menu's info line is legibly faded.
