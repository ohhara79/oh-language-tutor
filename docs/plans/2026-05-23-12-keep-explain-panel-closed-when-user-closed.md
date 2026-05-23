# Keep explain panel closed when the user closed it mid-stream

## Context

Clicking **Explain** opens the panel (`.line.active`) and streams chunks in.
Users often close the panel mid-stream — tapping the raw text of the same
line, or tapping a different line — to keep reading while the LLM works in
the background. Today, the moment the explanation finishes the panel
auto-reopens, which fights the user's just-expressed intent.

Root cause: on completion, `WebSink.on_entry_explained()` re-renders the
entire `<section class="line">` with `active=True` and OOB-swaps it into the
DOM (`tutor/web_sink.py:119-132`). The outerHTML swap replaces the user's
just-closed element with one that always carries `.active`, so the CSS rule
`body.view-list .line:not(.active) .line-detail { display: none; }`
(`tutor/static/app.css:450`) shows the panel again.

## Approach

Client-side only. In `tutor/static/app.js`, add an `htmx:oobBeforeSwap`
listener: when the existing OOB target is a streaming line that the user
closed (has `.streaming`, no `.active`), strip `.active` from the incoming
fragment before the swap.

```js
document.body.addEventListener('htmx:oobBeforeSwap', (evt) => {
    const oldEl = evt.detail && evt.detail.target;
    const fragment = evt.detail && evt.detail.fragment;
    if (!oldEl || !fragment || !oldEl.classList) return;
    if (!oldEl.classList.contains('streaming')) return;
    if (oldEl.classList.contains('active')) return;  // user kept it open
    const newEl = fragment.firstElementChild;
    if (newEl && newEl.classList) newEl.classList.remove('active');
});
```

Implementation note: in htmx 2.x, for `outerHTML` OOB swaps,
`evt.detail.fragment` is a `DocumentFragment` (not the element). The cloned
`<section>` lives at `fragment.firstElementChild`, which is what must be
mutated. Targeting the fragment itself silently no-ops because
`DocumentFragment.classList` is `undefined`.

The pre-swap target already carries the answer to "did the user close it?",
so no extra tracking set or data attribute is needed. The
`on_explain_aborted` path renders with `active=False`, so abort handling is
unaffected.

## Verification

Manual browser test:
- Click Explain → close mid-stream → wait for completion → panel stays
  closed; tapping the raw text re-opens it with the rendered explanation.
- Click Explain → expand a different line while streaming → original line
  stays closed when its stream completes.
- Click Explain and don't close → panel stays open and renders the finished
  explanation (happy-path regression).
- Two-tab: close in tab A, leave open in tab B → completion respects each
  tab's local state.
