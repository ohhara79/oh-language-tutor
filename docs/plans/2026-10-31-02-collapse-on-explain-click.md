# Collapse line on Explain; blue indicator only when ready

## Context

Clicking **Explain** returned the line in its streaming state with `.active`
forced on, so the panel stayed open while the LLM streamed. The streaming
line also carried `.has-explanation`, so the blue left border appeared before
any explanation existed.

Desired: clicking Explain collapses the line; the blue border appears only
once the explanation is finished, signalling "ready — tap to open".

## Approach

- `tutor/web_sink.py` `render_line`: `streaming` no longer implies `active`.
  `on_entry_explained` renders the completed line collapsed.
- `tutor/web.py` explain endpoint: the "already explained" short-circuit also
  returns the line collapsed. The language-mismatch error path stays open.
- `tutor/templates/partials/line.html`: `.has-explanation` only when
  `entry.explanation` is set (not while streaming).
- `tutor/static/app.css`: gray dashed left border on `.line.streaming` so the
  user can see an explain is in progress while the line is collapsed.
- `tutor/static/app.js` `htmx:oobBeforeSwap`: inverted — if the user opened
  the line mid-stream to watch, add `.active` to the completed fragment so it
  stays open; otherwise it lands collapsed.
- Tests assert the streaming and completed fragments carry no `active`.

## Verification

- `uv run --frozen pytest`, `make lint`.
- Manual: Explain → collapses with gray cue; completion → blue border, still
  collapsed; opening mid-stream → stays open on completion; mismatch error →
  line stays open showing the error.
