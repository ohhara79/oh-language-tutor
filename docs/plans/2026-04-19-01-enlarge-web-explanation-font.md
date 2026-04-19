# Enlarge web explanation font to match raw text

## Context

On desktop, raw text (`.raw-toggle`) renders at 1.5rem (~24px) while the rendered explanation (`.explanation-body`) has no explicit `font-size` and falls back to the browser default (~16px). The ~8px gap is exaggerated by the font-family difference: raw is monospace (`ui-monospace`), explanation is the proportional body font (`system-ui`), and the monospace glyphs feel visually heavier.

On mobile the imbalance is masked — mobile browsers automatically inflate small text for readability, so the 16px explanation gets boosted while the already-large raw stays put, and the two end up appearing similar.

The gap was introduced by commit 06fd558 ("Enlarge font size"), which bumped `.raw-toggle` only. This plan adds a matching `font-size` to `.explanation-body` so desktop stays balanced and mobile needs no autosizing.

## Change

**File:** `tutor/static/app.css` at line 53 — add `font-size: 1.5rem` to the existing `.explanation-body` rule:

```css
.explanation-body { font-size: 1.5rem; margin: 0 0 0.5rem; }
```

No HTML or Python changes. Nested elements inherit automatically:

- `code` (`app.css:194`) is `0.9em` (relative) → scales to ~1.35rem.
- `<p>`, `<ul>`, `<strong>`, `<em>`, `<blockquote>` all inherit the size.
- `body` `line-height: 1.55` (`app.css:8`) remains appropriate.

## Out of scope

- `.msg.assistant` in the thread conversation (`app.css:166`) also renders markdown and currently inherits the body default. Leaving it alone for now — if thread conversations feel imbalanced later, apply the same `font-size: 1.5rem` to `.msg` or `.msg.assistant` as a follow-up.

## Verification

1. `make lint` — confirm tooling stays clean.
2. Launch the web UI and open it on desktop.
3. Confirm raw text and explanation text appear visually balanced (both ~24px).
4. Check mobile (real device or DevTools responsive mode at ~360 px): the two remain comparable — no regression from mobile text inflation.
5. Toggle OS dark mode: colors and layout unchanged.
6. Note: CSS is cache-busted by the `?v={{ version }}` query string in `tutor/templates/index.html`; hard-reload (Ctrl+Shift+R) or restart the app to pick up the change in an already-open browser.
