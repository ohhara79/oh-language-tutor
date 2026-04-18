# Sticky-bottom auto-scroll

## Context

`tutor/static/app.js` currently force-scrolls unconditionally whenever DOM mutates under `#stream-pane` or `#thread-conversation`:

```js
new MutationObserver(() => {
    if (current().view === 'list') {
        window.scrollTo(0, document.body.scrollHeight);
    }
}).observe(stream-pane, ...);

new MutationObserver(() => {
    const c = document.getElementById('thread-conversation');
    if (c) c.scrollTop = c.scrollHeight;  // no-op: .thread-conversation has no overflow
}).observe(thread-conversation, ...);
```

Result: while the user scrolls up to re-read earlier content, a new SSE entry or chunk yanks them back to the bottom. The thread-conversation observer is additionally a no-op (the element has no scroll region of its own — the page scrolls).

Goal: auto-scroll only when the user is already at (or within a small tolerance of) the bottom. Scrolling up pauses auto-scroll; scrolling back to the bottom resumes it. Same rule in both list view and thread-detail view. Both views use page-level scrolling.

## Change — `tutor/static/app.js` only

Track `wasAtBottom` via a passive window scroll listener and gate both observers on it. Replace the no-op per-element scroll in the thread-conversation observer with a window scroll so auto-scroll actually works in thread-detail view.

```js
const NEAR_BOTTOM_PX = 32;
function isWindowAtBottom() {
    return window.innerHeight + window.scrollY >= document.body.scrollHeight - NEAR_BOTTOM_PX;
}

let wasAtBottom = true;  // empty page counts as "at bottom"
window.addEventListener('scroll', () => {
    wasAtBottom = isWindowAtBottom();
}, {passive: true});

// Initialize once the static DOM is in place.
document.addEventListener('DOMContentLoaded', () => {
    wasAtBottom = isWindowAtBottom();
});

// Stream pane: new entries (list view only).
new MutationObserver(() => {
    if (current().view !== 'list') return;
    if (!wasAtBottom) return;
    window.scrollTo(0, document.body.scrollHeight);
}).observe(document.getElementById('stream-pane'), {childList: true, subtree: true});

// Thread conversation: streaming chunks (thread-detail view only).
new MutationObserver(() => {
    if (current().view !== 'thread') return;
    if (!wasAtBottom) return;
    window.scrollTo(0, document.body.scrollHeight);
}).observe(document.getElementById('thread-conversation'), {childList: true, subtree: true});
```

Notes:
- The scroll listener updates `wasAtBottom` on every scroll — including the programmatic `scrollTo` emitted by the observer (the self-scroll keeps the flag true). Manual user scroll up → flag goes false → subsequent mutations don't scroll. Scroll back down → flag true → resumes.
- `NEAR_BOTTOM_PX = 32` absorbs small rounding differences (subpixel fractions, varying row heights) so "at bottom" actually triggers.
- Gate by `current().view` so the hidden pane's mutations (e.g. SSE while in thread-detail) don't move the visible pane.
- `distributeThreads()` still mutates `.line-threads` under `#stream-pane`, which fires the observer; with the gate, auto-scroll only happens if the user is at the bottom — preserving intent.

## Verification
1. `node --check tutor/static/app.js` — syntax.
2. `uv run --frozen ruff check tutor/ && uv run --frozen basedpyright tutor/` — clean (Python untouched).
3. Browser:
   - Fresh list view with a few entries at bottom → new SSE entry auto-scrolls to bottom.
   - Scroll up to read earlier entries → new SSE entry arrives → page stays put (no yank).
   - Scroll back down to the last entry → auto-scroll resumes on the next entry.
   - Thread-detail view: send a message → streamed chunks auto-scroll while viewing the tail; scroll up mid-stream → page stays put; scroll back → resumes.

## Critical files
- `tutor/static/app.js`
