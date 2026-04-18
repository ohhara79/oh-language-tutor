# Preprocess markdown to render loose lists

## Context

Tutor explanations and thread replies that contain a heading-like line immediately followed by `- ` bullet items render as a single run-on paragraph in the web UI (e.g. "Vocabulary: - farm → 농장 - pen → 우리 - …"). The tutor.json payload confirms the model **does** emit `\n` between lines — but Python-markdown requires a blank line before a list to recognize it as `<ul>`. Without that blank line, the whole block stays inside `<p>`, and the browser collapses the interior newlines into single spaces.

We want the renderer to accept the model's natural output (list directly under a heading line, no blank line) and still produce proper `<ul><li>…</li></ul>`.

## Approach

Add a small preprocessor in `tutor/markdown_util.py` that inserts a blank line **before** any list-marker line that immediately follows a non-blank, non-list line. Run it before `emphasis_to_html` / `md.markdown` so both the web UI, the TUI markdown path, and the HTML exporter all benefit from one change.

### Critical file

- `tutor/markdown_util.py` — add preprocessor, call it from `render_markdown`.

### New helper (sketch)

```python
_RE_LIST_MARKER = re.compile(r'^\s*([-*+]|\d+\.)\s')

def _insert_blank_before_lists(text: str) -> str:
    """Ensure a list-marker line that follows non-list text has a blank line before it."""
    lines = text.split('\n')
    out: list[str] = []
    for line in lines:
        if (
            _RE_LIST_MARKER.match(line)
            and out
            and out[-1].strip()
            and not _RE_LIST_MARKER.match(out[-1])
        ):
            out.append('')
        out.append(line)
    return '\n'.join(out)
```

### Wire-up

```python
def render_markdown(text: str) -> str:
    text = _insert_blank_before_lists(text)
    return md.markdown(emphasis_to_html(text), extensions=['extra', 'sane_lists'])
```

Scope notes:
- Only top-level list markers (`-`, `*`, `+`, `\d+.`). Indented/continuation lines keep current behavior.
- No change to `_RE_STRONG` / `_RE_EMPH` or the `extra` + `sane_lists` extensions.
- Reuses the single `render_markdown` entry point that is already called from `tutor/web_sink.py` (explanations + thread completion), `tutor/templates/partials/thread_conversation.html` (stored thread replay), `tutor/html_export.py`, and `tutor/tui.py`.

## Verification

1. `uv run --frozen python -c "from tutor.markdown_util import render_markdown; print(render_markdown('Vocabulary:\n- a → 가\n- b → 나\n\nNext'))"` — expect `<p>Vocabulary:</p>\n<ul>\n<li>a → 가</li>\n<li>b → 나</li>\n</ul>\n<p>Next</p>`.
2. Regression: same call on `'\n\n- a\n- b'` (already-correct input) should produce the same `<ul>` without a spurious blank line.
3. Regression: plain paragraph with a trailing "word - word" (e.g. `"battery - cell"`) should **not** grow into a list (the hyphen isn't at line start).
4. `uv run --frozen basedpyright tutor/markdown_util.py`.
5. Run the app end-to-end (`uv run --frozen python main.py` or whichever existing entry), trigger a vocab-style explanation in the browser, confirm bullets render and the `tutor.json` payload is unchanged.
