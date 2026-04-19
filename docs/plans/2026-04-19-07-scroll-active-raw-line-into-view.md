# Scroll newly-expanded raw-text line to top on toggle

## Context

In the web UI list view, tapping a raw-text line inline-expands an explanation panel below it (`.line.active .line-detail`). Because the previously-active line collapses at the same time, the vertical layout above the newly-clicked line can shift, and if the clicked line sits low in the viewport the revealed explanation renders below the fold. The user has to scroll manually to read it.

The fix: whenever a line becomes the newly-active one, align that line's raw-toggle button to the top of the scroll viewport so the raw text sits at the top and its explanation is visible beneath it.

## Approach

Extend the existing click handler in `tutor/static/app.js` (the `#stream-pane` listener that toggles `.active`). After the class toggle, if the click *opened* a line (i.e. `wasActive === false`), call `scrollIntoView({block: 'start', behavior: 'smooth'})` on that line element.

No scroll adjustment is needed when the click *collapses* the currently-active line (toggle-off), since the user's scroll context there is already correct.

The CSS rule that gates visibility (`body.view-list .line:not(.active) .line-detail { display: none; }`) already guarantees that by the time `scrollIntoView` runs, the newly-active `.line-detail` participates in layout, so the browser scrolls to the real final position. No `requestAnimationFrame` deferral is needed.

## Files to modify

- `tutor/static/app.js`

### Edit in `tutor/static/app.js`

In the `#stream-pane` click handler, after adding `.active` to the newly-opened line, call `scrollIntoView` on that line:

```js
if (!wasActive) {
    line.classList.add('active');
    line.scrollIntoView({block: 'start', behavior: 'smooth'});
}
```

No HTML/template or CSS changes required.

## Verification

1. Run the web server locally and open the list view in a browser.
2. Ensure the stream has enough lines that several fit per viewport and the list is scrollable.
3. Click a line near the top — its explanation expands below it; viewport scrolls so the raw text sits at the top.
4. Click a different line that was previously below the fold — viewport scrolls smoothly so that newly-clicked line's raw text is at the top and its explanation is immediately visible without manual scroll. This is the reported bug path; confirm fixed.
5. Click the currently-active line again — it collapses and no scroll jump happens.
6. Switch to thread-detail view and back to list view — the click behavior in thread-detail is unaffected (the handler early-returns when `current().view !== 'list'`).
7. `make lint` passes.
