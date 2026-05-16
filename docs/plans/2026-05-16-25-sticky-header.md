# Sticky header so the hamburger menu stays reachable on mobile

## Context

After the previous change consolidated "Switch dataset" and the "Show only explained" filter into a hamburger menu in the top-right of the page header, the menu is only reachable from the top of the document. On mobile, with a long sentence list, scrolling all the way back to the top to switch dataset or toggle the filter is impractical.

Fix: pin the existing `<header>` to the top of the viewport with `position: sticky`. No markup change, no JS, no server change — a single CSS rule extension. The dropdown panel already absolute-positions itself relative to `<header>` (see `.menu-panel` at `tutor/static/app.css:35-46`), so it will follow the sticky header automatically.

## Approach

Extend the existing `header` rule at `tutor/static/app.css:11-16` with three properties:

```css
header {
    position: sticky;           /* was: position: relative */
    top: 0;
    background: Canvas;         /* opaque so scrolled content doesn't bleed through */
    z-index: 30;                /* above stream content, below toasts (z-index: 100) */
    border-bottom: 1px solid #888;
    margin: 0 -1rem 1rem;
    padding: 0.75rem 1rem;
}
```

Why each property:

- **`position: sticky; top: 0`** — pins the whole header to the top of the viewport during scroll. `sticky` still establishes a containing block for absolutely-positioned descendants (same as `relative`), so the existing `.menu-panel { position: absolute; top: 100%; right: 1rem }` (`tutor/static/app.css:34-46`) continues to drop down correctly from the now-sticky header. No change needed to the panel.
- **`background: Canvas`** — without an opaque background, sentence content would show through as the user scrolls under the header. `Canvas` is a CSS system color (already used by `.menu-panel` at `tutor/static/app.css:39`) that resolves to the user-agent's canvas color in both light and dark modes; this dovetails with the existing `color-scheme: light dark` declaration at `tutor/static/app.css:1` and matches close enough to the dark-mode override `body { background: #1a1a1a }` (`tutor/static/app.css:385`) that there's no visible seam.
- **`z-index: 30`** — places header (and the menu-panel nested in it, which has its own `z-index: 50` within the header's stacking context) above stream lines (default stacking) but below the existing toast container at `z-index: 100` (`tutor/static/app.css:351`). Streaming error toasts therefore still appear over an open menu, which is the right priority.

Whole-header sticky (title + banner + hamburger) is chosen over sticky-only-row to avoid splitting the existing markup. Cost is ~3rem of permanent vertical real estate, which is acceptable on the 44rem-max-width layout.

## Files to modify

- `tutor/static/app.css` — extend the `header { ... }` rule at lines 11-16 with `top: 0;`, `background: Canvas;`, `z-index: 30;`, and change `position: relative` to `position: sticky`.

No changes to:
- `tutor/templates/index.html` (markup already supports a sticky parent for the panel).
- `tutor/static/app.js` (no scroll listener or behavior change required).
- `tutor/web.py` and `tutor/templates/partials/*` (no server-side work).

## Verification

Manual (no test framework configured):

1. `make lint` clean.
2. Run web mode, open `/tutor` on a dataset with many entries.
3. **Desktop:** scroll halfway down the stream → header (title row, banner, hamburger) stays pinned at the top of the viewport. Click the hamburger → dropdown still drops from the header. Toggle "Show only explained" while scrolled → filter applies; header remains pinned. Click "Switch dataset" → returns to `/`.
4. **Mobile (or DevTools device emulation):** repeat step 3 on a narrow viewport; confirm the hamburger is one tap away regardless of scroll position.
5. **Dark mode:** toggle OS dark mode; confirm the sticky header background does not visibly differ from the page background under scrolled content (`Canvas` vs `#1a1a1a` should be near-indistinguishable; if a seam appears, fall back to `background: light-dark(#fff, #1a1a1a)`).
6. **Thread view:** click "Ask" on an explained line to enter thread view → `#stream-pane` hides, header remains at top, hamburger still tappable. The `#thread-topbar` Back button still appears below the header and works as before.
7. **Toast precedence:** trigger an error (e.g. open a thread on a deleted entry) → the toast renders above the header even when the menu is open.
8. **Streaming under header:** start an "Explain" → tokens stream into a line below the header without overlapping or visual glitches as you scroll.
