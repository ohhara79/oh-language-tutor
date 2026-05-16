# Fix stale `on_thread_done` tests asserting removed `msg-stream` id

## Context

`make test` fails with 2 errors in `tests/test_web_sink.py`:

- `test_on_thread_done_with_text_renders_markdown` (line 114)
- `test_on_thread_done_empty_text_empty_placeholder` (line 124)

Both assert that the fragment emitted by `WebSink.on_thread_done` contains
`id="msg-stream-tid"`. The source no longer emits that id —
`7218ddb Fix duplicated follow-up reply caused by stale msg-stream id.`
deliberately removed it because a duplicate id on the finalized assistant
div caused OOB swaps (`querySelectorAll`) to hit both elements on the next
turn, overwriting the previous answer. The finalized div now targets the
live placeholder via the OOB selector instead:

```html
<div class="msg assistant" hx-swap-oob="outerHTML:#msg-stream-tid">…</div>
```

The implementation (`tutor/web_sink.py:136-147`) is correct and
load-bearing for follow-up turns. The tests were not updated alongside
the fix. Update them.

## Approach

Update the stale id assertion to check the OOB selector that now carries
`thread_id`. The empty-text test's `endswith('></div>')` assertion remains
valid and stays.

### `tests/test_web_sink.py:114`

Replace:
```python
assert 'id="msg-stream-tid"' in fragment
```
with:
```python
assert 'hx-swap-oob="outerHTML:#msg-stream-tid"' in fragment
```

### `tests/test_web_sink.py:124`

Same replacement.

## Files

- `tests/test_web_sink.py` — two one-line assertion updates.

No source/production code changes.

## Verification

1. `make test` — 154 passed (was 152 passed + 2 failed).
2. `make lint` — basedpyright + ruff clean.
