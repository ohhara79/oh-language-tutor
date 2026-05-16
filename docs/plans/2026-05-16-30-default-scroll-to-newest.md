# Scroll /tutor to the newest sentence on initial load

## Context

After removing the lazy-loader (commit `e76b097`), `GET /tutor` now renders the entire dataset in a single page. The browser's natural default scroll position is the **top** of the document, which means the user lands on the **oldest** sentence first. Previously the page only contained the last 500 entries and (by virtue of the prior layout) tended to start near the bottom, so the user typically saw the newest content immediately.

The user wants the default scroll position to be the **last** (newest) sentence — i.e. open the dataset and see what was just written, not what was written first.

Side-benefit: this matches the existing "follow the stream" SSE behavior (`wasAtBottom` auto-scrolls new entries into view), the slider's default value (initialized to `N` = newest), and the chat-app convention.

## Approach

Single change in `tutor/static/app.js`: after the existing `distributeThreads()` call on initial mount (line 311), scroll the window to `document.body.scrollHeight` so the page starts at the bottom.

Snippet to insert immediately after `distributeThreads();`:

```js
// On initial /tutor load, land on the newest sentence rather than the
// oldest. Matches the slider's default value (N = newest) and the
// SSE follow-the-stream auto-scroll behavior.
window.scrollTo(0, document.body.scrollHeight);
```

Notes:
- The `<script src="/static/app.js">` tag sits at the end of `<body>`, so by the time the IIFE runs, every `.line` element is in the DOM and `scrollHeight` reflects the full document.
- `wasAtBottom` is initialized to `true` (line 320). After our programmatic scroll fires the `scroll` event listener (line 321), `isWindowAtBottom()` will re-evaluate to `true`, so the flag stays in sync — SSE auto-scroll continues to work as before.
- Empty dataset: `scrollHeight` is just the viewport height, so `scrollTo(0, scrollHeight)` is effectively a no-op. No special case needed.
- Browser back/forward navigation does not re-trigger the IIFE (the list↔thread transition is JS push/pop, not a real page load), so the browser's restored scroll position is preserved as today.

## File to modify

- `tutor/static/app.js` — one-line addition after `distributeThreads();` at the current line 311.

## Verification

1. `make lint` — should remain clean.
2. Pick a dataset with many entries (e.g. the existing `bladerunner.srt`-derived state dir) and open `/tutor` in a browser. The viewport should land at the bottom of the page with the most recent sentence visible just above the page bottom.
3. Open `/tutor` on a dataset with **zero** entries. The page should render cleanly with no JS errors; nothing meaningful to scroll to.
4. With the page open at the bottom, append a new entry via the writing flow (stdin → writing_dir). Confirm the existing SSE auto-scroll still slides the new entry into view (i.e. our change did not desync `wasAtBottom`).
5. Scroll up manually, then click a line to open a thread, then press Back. Confirm the list view's restored scroll position is preserved (we are *not* forcing scroll-to-bottom on every render — only on the initial IIFE run).
