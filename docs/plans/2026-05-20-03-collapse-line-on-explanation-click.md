# Collapse line on explanation click in list view

## Context

In raw text list view, clicking the raw-text button toggles the line open/closed
while still allowing text selection / copy (`tutor/static/app.js:238-290`,
drag-detection + selection-detection guards). The explanation panel (`div.explanation-body`)
inside the expanded `.line-detail` currently has no click affordance — to collapse
an expanded line the user must scroll back up and click the raw text again.

Goal: clicking the explanation should collapse the line, mirroring the raw-text
toggle. Selection (drag) inside the explanation must continue to work so the
user can copy text. Links inside the rendered explanation must remain clickable.

## Approach

Extend the existing pointerdown / click handlers in `tutor/static/app.js` to
also treat `.explanation-body` (the non-streaming variant) as a collapse
trigger, reusing the same drag-distance and selection guards already used for
`.raw-toggle`. The shared "toggle `.line.active`" branch handles both cases:
clicking an explanation on an active line removes `active` (collapse); the
inactive case is unreachable because `.line-detail` is hidden when the line
isn't active.

Skip the click when the target is inside an interactive child of the
explanation (`<a>`) so markdown links keep working. Streaming explanations
(`.explanation-body.explain-stream-body`) are excluded — they're transient
output, not a stable collapse target.

Add `cursor: pointer` to `.explanation-body` in list view only so the
affordance matches `.raw-toggle`. `<a>` cursors override naturally.

## Files to modify

- `tutor/static/app.js` (lines ~244-290) — change the toggle target lookup
  from `.closest('.raw-toggle')` to also match `.explanation-body:not(.explain-stream-body)`.
  In the click handler, when the matched element is an `.explanation-body`,
  bail if `e.target.closest('a')` is non-null (so markdown links work). The
  existing drag-distance check (`DRAG_PX`), selection check (`window.getSelection`),
  and `.line.active` toggle branch all apply unchanged. The scroll-into-view
  call at the end is fine for the collapse case too — it keeps the raw text
  in view.
- `tutor/static/app.css` (near line 194) — add `cursor: pointer;` to
  `body.view-list .explanation-body:not(.explain-stream-body)`. Selection
  is already enabled for `<div>` by default; no `user-select` rule needed.

## Verification

1. Start the app, open list view with an entry that has an explanation.
2. Click the raw text → line expands. Click the explanation body → line
   collapses. Click raw text again → reopens.
3. Select text inside the explanation by dragging. Releasing the mouse
   should NOT collapse the line. The selection should remain so the user
   can copy (Ctrl+C / Cmd+C).
4. If the rendered explanation has a markdown link, clicking it navigates
   normally and does not collapse the line.
5. Clicking the Ask / Delete buttons inside `.line-actions` continues to
   submit those forms (they're siblings of `.explanation-body`, so
   `closest('.explanation-body')` doesn't match — no regression).
6. Trigger an Explain to produce a streaming response; clicking the
   streaming output area must NOT collapse the line (excluded via
   `:not(.explain-stream-body)`).
7. Run `make lint`.
