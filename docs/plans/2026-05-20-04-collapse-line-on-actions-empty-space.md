# Collapse line on line-actions empty-space click in list view

## Context

Follow-up to `2026-05-20-03-collapse-line-on-explanation-click.md`. That change
made clicking the rendered explanation collapse the line. The strip below it
(`.line-actions`, holding the Ask / Delete / Explain buttons) was still
non-collapsing dead space — to close an expanded line the user had to scroll
back to the raw text or click into the explanation body.

Goal: clicking empty space inside `.line-actions` should also collapse the
line, while the buttons themselves continue to submit their forms.

## Approach

Extend the `toggleTarget` helper in `tutor/static/app.js` to additionally
match `.line-actions`, reusing the existing drag / selection / `.line.active`
toggle pipeline. Add a guard in the click handler that bails when the click
target is on an interactive descendant (`button, a, input`) so the Ask /
Delete / Explain forms keep working.

The streaming variant of `.line-actions` only contains a status span — it has
no interactive children, so clicking it will collapse the line. That's
acceptable: the background stream continues, and reopening the line shows the
final result.

Add `cursor: pointer` to `.line-actions` in list view for affordance; button
cursors override naturally.

## Files to modify

- `tutor/static/app.js` — `toggleTarget` selector adds `.line-actions`; the
  click handler adds a `closest('button, a, input')` short-circuit for the
  `.line-actions` branch (matching the existing `<a>` short-circuit used for
  `.explanation-body`).
- `tutor/static/app.css` — `body.view-list .line-actions { cursor: pointer; }`.

## Verification

1. Expand a line by clicking its raw text. Click empty space inside the
   Ask / Delete row → line collapses.
2. Click the Ask button → opens the thread (does not collapse).
3. Click the Delete button → confirm prompt fires; on confirm the line is
   replaced (does not collapse first).
4. For a line without an explanation, expand it, then click empty space in
   the row containing the Explain button → line collapses. Click the Explain
   button itself → submits.
5. Drag-select text inside `.line-actions` (if any selectable text exists)
   → no collapse. The drag-guard handles this.
6. Run `make lint`.
