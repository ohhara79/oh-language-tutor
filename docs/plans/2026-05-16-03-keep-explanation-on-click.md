# Keep explanation open when clicking explanation text

## Context

Plan `2026-04-19-08-close-explanation-on-click.md` added a click-anywhere-inside-the-explanation gesture to collapse the line. In practice this fires when the user is trying to select text in the explanation or just tap-resting on it, so the panel collapses on the user mid-read. The collapse-by-clicking-explanation behavior is removed; only clicking the raw-text line (`.raw-toggle`) toggles expand/collapse. Clicking the explanation body is now a no-op.

## Approach

Trim the delegated click handler on `#stream-pane` in `tutor/static/app.js` so only `.raw-toggle` is a trigger:

- Drop the `.explanation-body` lookup and the link-exemption guard — both are unnecessary once explanation clicks are inert.
- Drop the `trigger = toggle || explanation` fallback; gate on `toggle` directly.
- Update the leading comment so it no longer mentions explanation-body as a collapse path.

The Ask / Delete buttons are siblings of `.explanation-body` inside `.line-detail` and continue to work through their own htmx form handlers. Links inside the explanation likewise bubble harmlessly with no special-case needed.

## Files to modify

- `tutor/static/app.js`

### Edit in `tutor/static/app.js`

Replace the `#stream-pane` click handler with:

```js
// Tap a raw-line toggle in list view -> inline-expand that line's detail.
// Clicking a different line collapses the previous one; clicking the same
// line again collapses it (toggle).
document.getElementById('stream-pane').addEventListener('click', (e) => {
    if (current().view !== 'list') return;
    const toggle = e.target.closest('.raw-toggle');
    if (!toggle) return;
    const line = toggle.closest('.line');
    if (!line) return;
    const wasActive = line.classList.contains('active');
    document.querySelectorAll('.line.active').forEach((el) => {
        el.classList.remove('active');
    });
    if (!wasActive) {
        line.classList.add('active');
    }
    line.scrollIntoView({block: 'start', behavior: 'smooth'});
});
```

No template or CSS changes.

## Verification

1. Run the web server and open the list view.
2. Click a sentence with no explanation yet → the per-line "Explain" button still works.
3. Click a sentence with an explanation → line expands and shows the explanation.
4. Click inside the explanation text → line stays expanded (was collapsing before).
5. Click a link inside the explanation, if any → link navigates as normal.
6. Click the same sentence again → line collapses.
7. Click a different sentence → previous collapses, new one expands.
8. `make lint` passes.
