# Label the per-line follow-up question list with a heading

## Context

A prior change (`docs/plans/2026-05-16-14-hide-line-threads-when-collapsed.md`)
moved `.line-threads` inside `.line-detail`, so past questions now appear under
the explanation body when a line is expanded. Without a heading, the list of
question titles reads as if it were a continuation of the explanation — there
is no visual cue that those clickable lines are separate threads the user
opened earlier.

Add a "Follow-ups" heading directly above the list, visible only when there is
at least one follow-up thread for that line.

## Approach

`distributeThreads()` in `tutor/static/app.js:208` is the single point where
`.line-threads` gets populated: it wipes every `.line-threads` container, then
appends a `<ul class="thread-list">` only for lines that actually have threads.
The existing CSS rule `.line-threads:empty { display: none; }`
(`tutor/static/app.css:120`) hides the container — and anything it contains —
when there are no threads.

Insert the heading element inside the same container, immediately before the
`<ul>`, in the same loop iteration. Because the heading lives *inside*
`.line-threads`, it is only rendered when threads exist (the wipe-and-rebuild
flow guarantees this), and the `:empty` rule never matches when the heading is
present — so the heading and the list show or hide together with no extra
conditional CSS.

No `:has()` selector, no template changes, no wrapper element.

## Changes

### `tutor/static/app.js` — `distributeThreads()`

In the per-line build loop, create an `<h3 class="line-threads-heading">` with
text `Follow-ups` and append it to the container before the `<ul>`:

```javascript
const heading = document.createElement('h3');
heading.className = 'line-threads-heading';
heading.textContent = 'Follow-ups';
container.appendChild(heading);
const ul = document.createElement('ul');
ul.className = 'thread-list';
list.forEach((li) => { ul.appendChild(li.cloneNode(true)); });
container.appendChild(ul);
```

The clear-then-rebuild flow (`c.innerHTML = ''`) already removes any stale
heading on every re-distribution, so this stays consistent when threads are
added, deleted, or anchors come/go.

### `tutor/static/app.css` — heading style + dark-mode override

Add a small, low-emphasis style so the label reads as a section header but
does not compete with the explanation body. Place near the existing
`.line-threads` rules, and add the dark-mode color inside the existing
`@media (prefers-color-scheme: dark)` block.

```css
.line-threads-heading {
    margin: 0 0 0.25rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

@media (prefers-color-scheme: dark) {
    /* ... */
    .line-threads-heading { color: #aaa; }
}
```

## Critical files

- `tutor/static/app.js` — `distributeThreads()`.
- `tutor/static/app.css` — new heading style + dark-mode override.

No changes to templates or Python.

## Verification

1. `make lint` — no regressions.
2. Run the dev server and open the web UI.
3. Find an explained line that already has at least one follow-up thread.
   Expand it. Confirm the heading "FOLLOW-UPS" appears immediately above the
   list and is visually distinct from the explanation body.
4. Find an explained line with no follow-ups and expand it. Confirm no heading
   is shown — the explanation body sits directly above the Ask/Delete buttons.
5. From an expanded line with no threads, click Ask, send a message in the
   opened thread, return to the line view. After the thread-list SSE swap,
   the heading should appear above the new thread entry.
6. Delete the only thread on a line. After re-distribution, the heading
   should vanish along with the list.
7. Toggle dark mode (OS preference) and confirm the heading color still reads
   well against the dark background.
