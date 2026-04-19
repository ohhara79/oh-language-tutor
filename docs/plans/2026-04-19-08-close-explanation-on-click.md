# Close explanation by clicking explanation text

## Context

In the web UI list view, tapping a raw-text line inline-expands an explanation panel below it, and tapping the same raw text again collapses the panel. The user wants a symmetric dismissal gesture: a click anywhere inside the explanation body should also collapse the line, so they don't have to hunt for the raw-text line (which may be out of view once the explanation is expanded). In addition, on collapse the raw-text line should be scrolled to the top of the viewport so the user has a stable anchor after the layout shrinks — currently the scroll-to-top behavior only runs on expand.

## Approach

Extend the delegated click handler in `tutor/static/app.js` that already lives on `#stream-pane`:

1. In addition to `.raw-toggle`, accept clicks that land inside `.explanation-body` as a trigger.
2. When the trigger is inside `.explanation-body`, ignore clicks that are on an `<a>` link so link navigation still works.
3. The existing `.line-actions` (Ask / Delete) buttons are unaffected because they are a sibling of `.explanation-body`, not nested inside it.
4. Move the `scrollIntoView({block: 'start', behavior: 'smooth'})` call out of the expand-only branch so it runs for both expand and collapse — keeping the raw-text line pinned at the top of the viewport in both directions.

Because the panel is visible at the time an `.explanation-body` click can occur, `wasActive` is always true on that path, so the `.active`-adding branch does not run and the net effect is a collapse.

## Files to modify

- `tutor/static/app.js`

### Edit in `tutor/static/app.js`

Replace the `#stream-pane` click handler body with:

```js
const toggle = e.target.closest('.raw-toggle');
const explanation = e.target.closest('.explanation-body');
if (explanation && e.target.closest('a')) return;
const trigger = toggle || explanation;
if (!trigger) return;
const line = trigger.closest('.line');
if (!line) return;
const wasActive = line.classList.contains('active');
document.querySelectorAll('.line.active').forEach((el) => {
    el.classList.remove('active');
});
if (!wasActive) {
    line.classList.add('active');
}
line.scrollIntoView({block: 'start', behavior: 'smooth'});
```

No HTML/template or CSS changes required.

## Verification

1. Run the web server locally and open the list view in a browser with enough entries to scroll.
2. Click a raw-text line → explanation expands and the raw-text line sits at the top of the viewport (existing behavior).
3. Click inside the explanation text of that line → explanation collapses and the raw-text line sits at the top of the viewport.
4. Click the raw text of an active line → it collapses and the raw-text line sits at the top of the viewport (new on the collapse path).
5. Expand a line and click the Ask or Delete button → the form submits; the panel does not collapse from the click itself.
6. If the rendered explanation contains a link, clicking the link navigates and does not collapse the panel.
7. Switch to thread-detail view → click handler early-returns (unchanged).
8. `make lint` passes.
