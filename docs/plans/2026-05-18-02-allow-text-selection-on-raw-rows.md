# Allow copy-paste text selection on raw-text rows

## Context

In the raw-text list view, each entry is rendered as `<button class="raw-toggle">{raw text}</button>` (`tutor/templates/partials/line.html:3`). A delegated `click` handler on `#stream-pane` (`tutor/static/app.js:241-255`) toggles the inline explanation panel for the clicked row.

This makes copy-pasting raw text broken in two ways:

1. A click-and-drag selection ends with a `click` event, which fires the toggle and immediately scrolls the row into view — collapsing the explanation (or expanding an unwanted one) and dropping the selection.
2. `<button>` elements inherit `user-select: none` from UA stylesheets on WebKit/iOS, so text inside may not even be selectable to begin with.

We want to keep the whole row tappable (and keyboard-accessible — the `<button>` stays), but ignore the toggle when the user was actually selecting text.

## Approach

Two coordinated changes.

CSS: explicitly opt the `.raw-toggle` button into text selection so Safari/iOS will let the user select its contents at all. No layout or color change.

JS: detect "this click was the end of a drag-selection" in the existing `#stream-pane` click handler and skip both the active-class toggle and the `scrollIntoView` in that case. Detection is the OR of two cheap signals:

- **Pointer moved**: a `pointerdown` listener on `#stream-pane` records `{x, y, t}` when the press lands on a `.raw-toggle`. In the click handler, if the distance from that point to the click's `clientX/Y` exceeds ~6 px, treat it as a drag, not a tap.
- **Non-empty selection inside this row**: at click time, if `window.getSelection().toString()` is non-empty AND the selection's `anchorNode` or `focusNode` is contained within the clicked `.raw-toggle`, treat it as a selection, not a tap.

Keyboard activation (Enter/Space on a focused button) doesn't fire `pointerdown`, so `lastPointer` will be `null` or stale; we treat "no fresh pointerdown" as a tap and let the toggle run. A small staleness window (1000 ms) guards against the case where a click somehow fires long after the corresponding pointerdown.

No HTML change. The `<button>` stays, preserving focus ring, keyboard activation, and a11y semantics.

## Files to change

- `tutor/static/app.css`
- `tutor/static/app.js`

### Edit 1 — `tutor/static/app.css`, inside the `.raw-toggle` block (lines 171–187)

Append two declarations so the button's text is selectable on all browsers (Safari/iOS in particular):

```css
.raw-toggle {
    /* ...existing declarations... */
    min-height: 44px;
    -webkit-user-select: text;
    user-select: text;
}
```

No `touch-action` override — the default still permits scroll and long-press for the native iOS selection menu, which is what we want.

### Edit 2 — `tutor/static/app.js`, replace the block at lines 241–255

Add a `pointerdown` listener that captures the press location, and gate the existing toggle on "this was a tap, not a drag-select."

```javascript
// Tap a raw-line toggle in list view -> inline-expand that line's detail.
// Clicking a different line collapses the previous one; clicking the same
// line again collapses it (toggle).
//
// We suppress the toggle when the click was actually the end of a
// text-selection drag, so the user can copy raw text. A click counts as
// a real tap unless either:
//   (a) the pointer moved more than DRAG_PX between pointerdown and click, or
//   (b) there is a non-empty selection whose anchor/focus lies inside the
//       clicked .raw-toggle.
// Keyboard activation (Enter/Space) has no pointerdown -> lastPointer is
// null/stale and we fall through to the tap path.
const DRAG_PX = 6;
const POINTER_STALE_MS = 1000;
let lastPointer = null;

const streamPane = document.getElementById('stream-pane');

streamPane.addEventListener('pointerdown', (e) => {
    if (current().view !== 'list') return;
    const toggle = e.target.closest('.raw-toggle');
    if (!toggle) {
        lastPointer = null;
        return;
    }
    lastPointer = {x: e.clientX, y: e.clientY, t: Date.now(), toggle};
});

streamPane.addEventListener('click', (e) => {
    if (current().view !== 'list') return;
    const toggle = e.target.closest('.raw-toggle');
    if (!toggle) return;

    // (a) Drag detection: only trust pointer data if it came from this same
    //     toggle and is fresh; otherwise treat as a tap (keyboard activation).
    const p = lastPointer;
    lastPointer = null;
    if (p && p.toggle === toggle && (Date.now() - p.t) < POINTER_STALE_MS) {
        const dx = e.clientX - p.x;
        const dy = e.clientY - p.y;
        if ((dx * dx + dy * dy) > (DRAG_PX * DRAG_PX)) return;
    }

    // (b) Selection inside this row -> user is selecting text, not tapping.
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.toString().length > 0) {
        const a = sel.anchorNode;
        const f = sel.focusNode;
        if ((a && toggle.contains(a)) || (f && toggle.contains(f))) return;
    }

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

Key points:

- `lastPointer` is cleared on every click (whether suppressed or not), so a previous drag can't leak into the next click.
- The `p.toggle === toggle` check covers the "select text in row A, then tap row B" case: the pointerdown on B replaces `lastPointer`; if it didn't, the stale pointer would have a different `toggle` and we'd fall through to the selection check, which correctly limits to selections inside *this* row.
- When we return early, we skip the active-class flip AND the `scrollIntoView`, preserving the user's selection and viewport.

## Not changing

- `tutor/templates/partials/line.html` — element stays a `<button>`. Keeping the button preserves Enter/Space activation, focus ring (`.raw-toggle:focus-visible`), and screen-reader semantics. Swapping to a `<div role="button">` would re-introduce all of that manually for no gain.
- Server / Python code — purely a client-side UX fix.
- The existing `.raw-toggle:hover` / `:focus-visible` styles, and the `.has-explanation` border-left from plan 01.

## Verification

Run the app and open the dataset view, then:

1. **Desktop click-drag**: press inside a raw line, drag across several words, release. Selection should remain visible and copyable (Cmd/Ctrl-C). The row should NOT toggle its explanation and should NOT scroll.
2. **Desktop simple click**: click once anywhere on a row's raw text without dragging. Explanation should toggle as before. Clicking a different row collapses the previous one and expands the new one (unchanged behavior).
3. **Desktop click + tiny jitter**: a normal click that moves 1–2 px (mouse hand wobble) must still toggle. The 6 px threshold absorbs this.
4. **Keyboard**: Tab to a `.raw-toggle`, press Enter, then press Space. Each press should toggle the explanation. (This is the no-pointerdown path; verifies the keyboard fallback.)
5. **Mobile tap (iOS Safari + Android Chrome)**: short tap toggles the explanation as before.
6. **Mobile long-press (iOS Safari)**: long-press inside raw text should bring up the native selection menu / handles, and releasing should NOT toggle the explanation (iOS does not fire `click` after a long-press that initiates selection).
7. **Cross-row selection cleanup**: select text in row A (don't toggle), then tap raw text in row B. Row B should toggle normally; the row-A selection is replaced by the new pointerdown on row B.
8. **Select then tap same row**: select text in row A, then tap raw text in row A again. The selection-inside-this-row check suppresses the toggle; user has to tap empty area or another row to dismiss the selection first. Acceptable trade-off — matches typical native-text behavior.
9. `make lint` to confirm no regressions.
