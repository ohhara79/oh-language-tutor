# Thread-header: let anchor text flow around the Delete button

## Context

In the web thread detail view, `.thread-header` uses `display: flex` with `justify-content: space-between` to put the anchor text on the left and the Delete button top-right (`tutor/static/app.css:141-148`). On narrow mobile viewports the anchor text wraps across multiple lines in the left column while the Delete button stays pinned top-right, so the horizontal space directly below the Delete button goes unused and the anchor is forced into an unnecessarily narrow column.

Fix: drop flex and float the Delete button, so the anchor text spans the full width and wraps *under* the button once it's taller than one line. Template and JS are untouched — this is a pure CSS change.

## Change

**File:** `tutor/static/app.css` — replace the `.thread-header` rule at lines 141–148 with:

```css
.thread-header {
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.5rem;
}
.thread-header::after {
    content: "";
    display: block;
    clear: both;
}
.thread-header > form {
    float: right;
    margin: 0 0 0.5rem 0.75rem;
}
```

`.anchor-raw` (lines 149–156) is unchanged — its existing `white-space: pre-wrap` and `word-break: break-word` already handle wrapping and long tokens.

## Why float (not grid / shape-outside / template refactor)

- CSS Grid can place items side-by-side or stacked but cannot make text *flow around* a fixed-size item.
- `shape-outside` is overkill for a rectangular button and requires a basic-shape or image.
- Making the button inline inside the `<p>` would be cleanest semantically but requires a template edit; this change is CSS-only.

## Edge cases handled

- **Short anchor** (single line): Delete sits right, anchor on the left, visually unchanged.
- **Long anchor** (many wrapped lines): text wraps under the button after the first ~1 line — the desired effect.
- **Anchor shorter than button height**: `::after` clear ensures the border-bottom sits below the button instead of cutting through it.
- **Dark mode**: no colors changed; existing `@media (prefers-color-scheme: dark)` rules still apply.
- **Next sibling** (`.thread-messages`): starts on a new line because the float is cleared by `::after`.

## Files

- `tutor/static/app.css` — edit `.thread-header` block (lines 141–148).
- `tutor/templates/partials/thread_conversation.html` — **reference only**, not modified.

## Verification

1. `make lint` — CSS isn't type-checked, but ensures nothing else regressed.
2. Start the web UI and open a thread in a browser.
3. Use DevTools responsive mode at ~360 px width:
   - Short anchor → Delete right-aligned, single-line anchor left, unchanged look.
   - Long anchor (multiple wrapped lines) → text wraps under the Delete button; no wasted space.
   - Border-bottom spans full width below both elements; no overlap.
   - `.thread-messages` below starts on its own line.
4. Check desktop width (≥768 px): visually indistinguishable from before.
5. Toggle OS/browser to dark mode: colors unchanged, layout identical.
