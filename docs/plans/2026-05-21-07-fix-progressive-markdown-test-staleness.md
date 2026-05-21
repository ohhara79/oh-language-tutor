# Fix stale chunk tests after progressive-markdown streaming

## Context

After commit `b791d09` ("Render markdown progressively while Explain/Ask
answers stream"), `make test` fails with two assertion errors in
`tests/test_web_sink.py`:

- `test_on_thread_chunk_broadcasts_escaped_fragment` (line 97)
- `test_on_explain_chunk_broadcasts_escaped_fragment` (line 184)

Both predate that commit. They feed raw HTML (`<script>x</script>`, `<b>x</b>`)
into `on_thread_chunk` / `on_explain_chunk` and assert it comes back
HTML-escaped. The new implementations
(`tutor/web_sink.py:130`, `tutor/web_sink.py:138`) instead accumulate the chunk
and run it through `render_markdown()`, so HTML passes through unchanged — by
design, per `docs/plans/2026-05-21-05-progressive-markdown-streaming.md`:
"the mid-stream look matches the final look exactly — no visual jump at the
end."

The sibling test `test_on_thread_done_with_text_renders_markdown`
(`tests/test_web_sink.py:108`) already validates the post-stream side of the
same pipeline by feeding `**bold**` and asserting `<strong>bold</strong>`
appears. The chunk tests should match that pattern.

## Approach

Test-only fix. Production code at `tutor/web_sink.py:130` and
`tutor/web_sink.py:138` is correct and stays untouched.

## Files

- `tests/test_web_sink.py` — rename and rewrite two tests so they exercise
  markdown rendering rather than HTML escaping:
  - `test_on_thread_chunk_broadcasts_escaped_fragment` →
    `test_on_thread_chunk_broadcasts_rendered_markdown`. Send `**bold**`,
    assert `hx-swap-oob="innerHTML:#msg-stream-tid-1"` and
    `<strong>bold</strong>` appear in the fragment.
  - `test_on_explain_chunk_broadcasts_escaped_fragment` →
    `test_on_explain_chunk_broadcasts_rendered_markdown`. Symmetric: send
    `**bold**`, assert `hx-swap-oob="innerHTML:#explain-stream-e-1"` and
    `<strong>bold</strong>` appear.

## Verification

1. `make test` — all 242 tests pass.
2. `make lint` — basedpyright + ruff stay clean.
