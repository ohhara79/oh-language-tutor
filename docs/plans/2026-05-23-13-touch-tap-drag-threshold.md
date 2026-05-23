# Fix touch taps being misclassified as drags

## Context

On touch devices (phone/tablet), tapping raw text in list view intermittently fails to open the explanation panel. After several retries it works. The user suspected this was related to "drag copy of the explanation", but the actual cause is unrelated to copying — the same tap-vs-drag detection logic that suppresses toggle when the user drag-selects text is also catching ordinary finger taps as if they were drags.

The handler in `tutor/static/app.js:344-350` distinguishes "tap to toggle" from "drag to select text" by measuring pointer movement between `pointerdown` and `click`. If the distance exceeds `DRAG_PX = 6` pixels, the toggle is suppressed.

`DRAG_PX = 6` is reasonable for mouse pointers but too tight for fingers. Even a deliberate finger tap typically registers 5–15px of jitter between `touchstart` and `touchend` (finger size, screen density, grip). When jitter exceeds 6px the tap is misclassified as a drag and the toggle is silently swallowed — explaining both the intermittency and the "several retries eventually works" behavior.

The selection guard at `tutor/static/app.js:352-357` is not the culprit — the user confirmed no drag-select happens beforehand.

## Change

`tutor/static/app.js:311` — bump the threshold:

```js
const DRAG_PX = 16;
```

No other lines change. The comparison at line 349 (`(dx * dx + dy * dy) > (DRAG_PX * DRAG_PX)`) continues to work as-is.

**Why 16px for both inputs:** comfortably above typical 5–15px finger jitter on touch, and still well under the width of a meaningful mouse drag — any intentional drag-to-select on desktop easily exceeds 16px. The selection guard at `tutor/static/app.js:352-357` is the primary defense against drag-select collisions (it inspects `window.getSelection()` directly), so the drag-distance check is just a secondary net for drags that released without producing a selection. 16px is plenty tight for that role.

**Why a single constant (not coarse-pointer-aware):** simpler — no `matchMedia`, no startup-vs-dynamic question, no extra code surface. The lower 6px value wasn't earning its keep on desktop because the selection guard already handled the common case.

## Verification

1. `make lint` — required by `CLAUDE.md`.
2. **Desktop sanity (no regression):** in a regular desktop browser, tap raw lines with the mouse — toggle still works. Click-drag across raw text to select — toggle still suppressed.
3. **Touch simulation:** Chrome DevTools → Device Toolbar → pick a phone preset. Tap raw lines repeatedly — should open every time, not intermittently. Mouse-drag ~20px across line text — toggle still suppressed.
4. **Real device check (preferred if available):** load the dev server on a phone, tap raw lines 10–20 times. Pre-fix: intermittent failures; post-fix: opens every time.

## Critical file

- `tutor/static/app.js` (one-line change at line 311)
