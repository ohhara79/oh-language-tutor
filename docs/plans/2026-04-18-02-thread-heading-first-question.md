# Thread list: show first question as heading

## Context

Thread list rows currently display the anchor raw text (the original source line) as the heading. When multiple threads hang off the same line, the heading is duplicated across every row — the user cannot tell threads apart without opening each one.

Change: use each thread's **first user message** as its heading. Fall back to `anchor_raw` for a just-opened thread that has no user message yet. Affects both the per-line inline thread lists (in list view) and the "Other threads" orphan section — both render through `partials/thread_list.html`.

## Changes

### `tutor/web.py`
Add helper alongside existing Jinja globals in `build_template_env()`:

```python
def thread_heading(meta: ThreadMeta) -> str:
    for m in meta.messages:
        if m.role == 'user':
            for line in m.text.splitlines():
                stripped = line.strip()
                if stripped:
                    return stripped
            break
    return meta.anchor_raw
```

Register:
```python
globals_['thread_heading'] = thread_heading
```

### `tutor/templates/partials/thread_list.html`
```html
<span class="anchor">{{ thread_heading(t) | e }}</span>
```

## SSE correctness
`WebSink.on_thread_list` re-renders the whole partial from current `ThreadMeta` objects, so after the first assistant reply on a new thread, the next `thread_list` broadcast carries the user message and `distributeThreads()` updates inline headings automatically.

## Not changing
- `thread_conversation.html` — detail view keeps `anchor_raw` (useful orientation).
- `html_export.py` — separate renderer, out of scope.
- No persistence or SSE schema change.

## Verification
1. `uv run --frozen ruff check tutor/` + `uv run --frozen basedpyright tutor/` — green.
2. Render `index.html` with two stub threads (one with user message, one empty) and assert the first shows the question, the second shows `anchor_raw`.
3. Browser: open a thread via Ask → heading is `anchor_raw`; send a question → after SSE redistribute, heading flips to the question.

## Critical files
- `tutor/web.py`
- `tutor/templates/partials/thread_list.html`
