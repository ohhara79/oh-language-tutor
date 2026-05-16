# Sync "Jump to" slider with current scroll position on menu open

## Context

The hamburger menu's "Jump to" control (`#jump-slider` + `#jump-current` in
`tutor/templates/index.html:25-34`) is a 1-based sentence-index slider. Its
displayed value is only ever changed by:

1. The user dragging the slider (`tutor/static/app.js:132-136`).
2. `jumpRefreshTotal()` clamping it down when the line count shrinks
   (`tutor/static/app.js:114-125`).
3. The initial value rendered by the template (defaults to `entries|length`).

There is no listener that updates the slider when the user scrolls the page
manually. So after a manual scroll, opening the hamburger shows a stale
"Jump to N / N" — usually the initial newest-line index, or the last value
the user dragged it to. That is the bug the user is reporting.

The page already knows how to identify the topmost visible line —
`topVisibleLineId()` at `tutor/static/app.js:315-322` is used to persist the
scroll anchor to `localStorage` on a debounced scroll listener
(`tutor/static/app.js:347-359`). We need the same notion (topmost visible
`.line`) expressed as a 1-based DOM index so the slider can adopt it.

## Approach

Recompute the slider's "current" value on demand when the hamburger menu is
about to be shown. This is the cheapest fix and matches user expectation
exactly — the slider is only visible when the menu is open, so a one-shot
refresh at open time is sufficient. (Updating on every scroll would also
work but adds per-scroll DOM writes for no perceptible benefit; the user
cannot see the slider while the menu is closed.)

## Changes

All edits are in `tutor/static/app.js`.

1. Add a small helper near the existing jump-slider helpers (after
   `jumpScrollTo` at ~line 131):

   ```js
   function topVisibleLineIndex() {
       const lines = jumpLines();
       for (let i = 0; i < lines.length; i++) {
           if (lines[i].getBoundingClientRect().bottom > 0) {
               return i + 1;
           }
       }
       return lines.length;
   }
   function jumpRefreshCurrent() {
       const n = jumpLines().length;
       if (n === 0) return;
       const idx = topVisibleLineIndex();
       jumpSlider.value = String(idx);
       jumpCurrent.textContent = String(idx);
   }
   ```

   `topVisibleLineIndex` mirrors the "first line whose bottom edge is
   below the viewport top" rule already used by `topVisibleLineId`, but
   returns a 1-based index over the same `jumpLines()` collection the
   slider is indexed against (so the math is consistent with
   `jumpScrollTo`).

2. Call `jumpRefreshCurrent()` from `setMenuOpen` when the menu is being
   opened (`tutor/static/app.js:78-81`):

   ```js
   function setMenuOpen(open) {
       if (open) jumpRefreshCurrent();
       menuBtn.setAttribute('aria-expanded', String(open));
       menuPanel.hidden = !open;
   }
   ```

No template, CSS, or Python changes are needed.

## Files

- `tutor/static/app.js` — add `topVisibleLineIndex` + `jumpRefreshCurrent`;
  call the latter from `setMenuOpen` on open.

## Verification

1. `make lint` — passes (no Python changes; JS isn't linted by the
   Makefile, but rerun anyway to confirm nothing else regressed).
2. Manual:
   - Start the dev server, load a dataset with many entries.
   - Scroll to somewhere in the middle of the stream.
   - Open the hamburger menu — "Jump to" should now read the index of the
     topmost visible sentence, not the total count or the last dragged
     value.
   - Drag the slider to a different value, close the menu, scroll
     elsewhere, reopen — the slider should snap to the new top-visible
     index rather than the dragged value.
   - With an empty dataset, opening the menu should not error (slider
     stays disabled at 0 / 0).
   - With "show only explained" filter on, the index still tracks the
     topmost line whose bottom is below 0 — hidden lines collapse to a
     zero-height box and are naturally skipped.
