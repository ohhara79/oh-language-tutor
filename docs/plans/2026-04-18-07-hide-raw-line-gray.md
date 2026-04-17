# Hide transient gray raw-line entries from web UI

## Context

Every stdin line triggers `sink.on_raw_line(...)` in `tutor/core.py:93`. In the web sink (`tutor/web_sink.py:65-68`) this both logs the line and broadcasts a `raw_line` SSE event (gray `.raw-line` div). `#stream-pane` subscribes to it (`sse-swap="explanation,raw_line"`) and appends the gray row. Explained entries render below but the gray row stays in DOM until reload — when rendering reads only persisted entries, so gray rows never appear.

Goal: never show gray rows. File log for `on_raw_line` stays.

## Change

### `tutor/templates/index.html`
```html
<main id="stream-pane" sse-swap="explanation" hx-swap="beforeend">
```

### `tutor/web_sink.py`
```python
def on_raw_line(self, raw: str) -> None:
    self._log.write(raw + '\n')
```

### `tutor/static/app.css`
Remove dead rules: `.raw-line { ... }`, `body.view-line .raw-line { display: none; }`, and the dark-mode `.raw-line { color: #888; }`.

## No change
- `tutor/core.py`, `tutor/sink.py`, `tutor/gui.py` — TUI still ticks raw lines via its own sink; protocol unchanged.

## Verification
1. `uv run --frozen ruff check tutor/ && uv run --frozen basedpyright tutor/` — green.
2. Render `index.html`; `stream-pane` has `sse-swap="explanation"` only.
3. Browser: feed stdin lines; no gray rows; explanations still stream. Reload identical. TUI unaffected.

## Critical files
- `tutor/templates/index.html`
- `tutor/web_sink.py`
- `tutor/static/app.css`
