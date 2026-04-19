# Enlarge raw text in thread detail view

## Context

In the web UI's thread detail view, the anchor raw text (`.anchor-raw` at
`tutor/templates/partials/thread_conversation.html:11`) renders at `0.9rem`,
which looks small on desktop. On mobile it appears larger because mobile
browsers auto-inflate small text for readability (same mechanism noted in
`2026-04-19-01-enlarge-web-explanation-font.md`).

By contrast, the raw anchor text shown in the list view (`.raw-toggle` in
`tutor/templates/partials/line.html`) is already `1.5rem`, and
`.explanation-body` was recently bumped to `1.5rem` (commit b2886ac). The
thread-detail header is the outlier.

## Change

**File:** `tutor/static/app.css` at line 151 — change `.anchor-raw`
`font-size` from `0.9rem` to `1.5rem` so it matches `.raw-toggle` and
`.explanation-body`:

```css
.anchor-raw {
    font-family: ui-monospace, monospace;
    font-size: 1.5rem;
    color: #555;
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
}
```

No media query needed — aligning the rem value with the size mobile
browsers already auto-inflate to equalizes desktop and mobile perceived
size. No HTML, Python, or dark-mode CSS changes. The dark-mode override
at `app.css:240` only sets color.

## Verification

1. `make lint` — confirm tooling stays clean.
2. Launch the web UI and open a thread detail view on desktop.
3. Confirm the anchor raw text is now visibly larger and matches the
   list-view raw lines.
4. Check mobile (real device or DevTools responsive mode): the text
   should look comparable to before, since mobile was already inflating
   it to a similar size.
5. Toggle OS dark mode: colors and layout unchanged.
6. Note: CSS is cache-busted by the `?v={{ version }}` query string in
   `tutor/templates/index.html`; hard-reload (Ctrl+Shift+R) or restart
   the app to pick up the change in an already-open browser.
