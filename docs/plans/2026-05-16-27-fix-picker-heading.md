# Fix picker-page heading dominating the mobile viewport

## Context

On the dataset picker page (`/`, rendered by `tutor/templates/picker.html`), the heading consumed ~90% of a mobile viewport, leaving almost no room for the dataset list and "Open" button. Two issues compounded:

1. **Regression from commit `4a55cf5`** ("Compact sticky header…"). That commit removed the `<h1>` from `index.html` and deleted `header h1 { margin: 0; font-size: 1.2rem; }` along with it, but the picker page still uses `<h1>oh-language-tutor</h1>` (`tutor/templates/picker.html:11`). It fell back to user-agent defaults (~2em font + ~0.67em top/bottom margins), adding ~5–6rem of vertical space.

2. **Unintended sticky.** The sticky `header` rule from commit `f49ebd9` applied to every page, including the picker. The picker is a short, single-screen chooser; pinning just compresses the area below without payoff.

Fix: a targeted CSS adjustment — re-add the compact `header h1` rule and scope the sticky behavior to non-picker views (`body:not(.view-picker)`). No template or JS changes.

## Approach

One file: `tutor/static/app.css`.

The current sticky `header` block was split into two rules:

```css
header {
    border-bottom: 1px solid #888;
    margin: 0 -1rem 1rem;
    padding: 0.75rem 1rem;
}
header h1 { margin: 0; font-size: 1.2rem; }

body:not(.view-picker) header {
    position: sticky;
    top: 0;
    z-index: 30;
    background: Canvas;
}
```

Notes:

- The `header h1` rule applies whether or not the page is sticky; the picker is the only template that currently uses an `<h1>` inside `<header>` (`tutor/templates/picker.html:11`), so it's effectively a picker-only rule today.
- Splitting the sticky-specific properties (`position`, `top`, `z-index`, `background`) into the scoped selector keeps the base `header` rule semantic (border/margin/padding only) and makes the sticky behavior obviously opt-in.
- `body.view-picker` is already set unconditionally by `tutor/templates/picker.html:9`. `app.js` only ever toggles `view-list` / `view-thread`, never `view-picker`, so the scope is correct for all states.

## Files modified

- `tutor/static/app.css` — header rule split as above; `header h1` re-added.

No changes to `tutor/templates/picker.html`, `tutor/templates/index.html`, `tutor/static/app.js`, or `tutor/web.py`.

## Verification

Manual (no test framework configured):

1. `make lint` clean.
2. Open `/` on mobile (or DevTools device emulation, e.g. iPhone SE 375×667 or smaller). Confirm the heading is compact: `<h1>` at ~1.2rem with no oversized margins, plus the one-line picker-sub paragraph. The dataset list and "Open" button are clearly visible without scrolling.
3. Scroll the picker (if there are many datasets) — header should *not* stay pinned at the top; it should scroll away normally, freeing the viewport.
4. Open `/tutor` — confirm the sentence-list header is still sticky, still single-row (dataset name + hamburger), still pinned when scrolling.
5. Open a thread via "Ask" — confirm the header is still sticky in thread-detail view.
6. Dark mode: confirm picker heading still readable (the existing `header { border-color: #444 }` dark override at app.css line 392 still applies via the base rule).
