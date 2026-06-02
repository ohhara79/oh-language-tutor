# Collapse a line by tapping its streaming explanation body

## Context

In list view, tapping a line's raw text expands its detail panel and tapping
again collapses it. Tapping the rendered (finished) explanation body also
collapses the line. **Tapping the explanation while it is still streaming
does nothing** — the user has to scroll back to the raw text to close it.

`toggleTarget` in `tutor/static/app.js` was excluding `.explain-stream-body`
on purpose ("transient output, not a stable collapse target"). But the
close-mid-stream flow is already wired end-to-end: commit `ea869dd` added an
`htmx:oobBeforeSwap` listener (`app.js:566-582`) that strips `.active` from
the completed-render fragment when the user closed the line mid-stream. The
only path that *triggered* that close-during-stream was tapping the raw
text or another line; the streaming body itself was inert.

The streaming body should behave the same as the finished body: tap anywhere
in it to collapse.

## Approach

- `tutor/static/app.js`: drop the `.explain-stream-body` early-return from
  `toggleTarget`. The streaming `<div>` already carries both
  `.explanation-body` and `.explain-stream-body`
  (`tutor/templates/partials/line.html:31`), so the closest-match falls back
  to `.explanation-body` and the rest of the click handler works unchanged:
  - The markdown-link guard checks `.explanation-body`, which also matches
    `.explain-stream-body` — links streamed mid-render still navigate.
  - The selection / drag guards are class-agnostic — drag-to-copy still
    suppresses the toggle.
  - Toggling `.line.active` off plus the existing `htmx:oobBeforeSwap`
    handler keeps the line collapsed once the stream finishes.
  - Update the explanatory comment block above the listener.
- `tutor/static/app.css`: drop the `:not(.explain-stream-body)` filter on
  the `cursor: pointer` rule so the streaming body advertises that it's
  tappable.

No template, server, or test changes are needed.

## Verification

Run with `uv run --frozen` and in list view:

1. Tap **Explain** on a line. While it's still streaming, tap inside the
   streaming text → the panel collapses and the stream continues.
2. Wait for the stream to complete → the line stays collapsed.
3. Tap the raw text again → the fully rendered explanation appears; tap it
   again → collapses (regression check for the existing behavior).
4. During streaming, drag-select some streamed text and release → selection
   sticks, the line does **not** collapse.
5. If a streamed chunk contains a markdown link, tap it → it navigates,
   does not collapse.
6. `make lint`.
