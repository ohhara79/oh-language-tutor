# Force Vocabulary items to render as a bulleted list

## Context

The `📚 Vocabulary` section of an explanation is supposed to show several
items, one per line as a bulleted list. In practice the items sometimes
collapse into a single run-on paragraph instead.

The rubric template at `tutor/prompts.py:303` was:

```python
rows.append(f'  \U0001f4da Vocabulary: <2-3 items, {source_language} word [pronunciation] → {target_language}>')
```

The placeholder `<2-3 items, …>` is ambiguous about layout. The model is
free to emit either of these, and both technically satisfy the rubric:

```
📚 Vocabulary: 사과 [sa-gwa] → apple, 배 [bae] → pear, 감 [gam] → persimmon
```

```
📚 Vocabulary:
- 사과 [sa-gwa] → apple
- 배 [bae] → pear
- 감 [gam] → persimmon
```

Only the bulleted form survives `render_markdown()` in
`tutor/markdown_util.py` as a `<ul>`. The comma-separated form has no
list markers, so `_insert_blank_before_lists()` can't help and it
renders as one long `<p>`. The other rubric rows (Translation,
Expression, Context) are single-line by design, so this is unique to
Vocabulary.

While fixing the layout, also widen the item count from 2-3 to 2-5: 3 is
often too few.

## Approach

Make the prompt template itself show the bulleted layout, so the model
pattern-matches it instead of guessing from a one-line placeholder:

```python
rows.append(
    f'  \U0001f4da Vocabulary:\n'
    f'  - <{source_language} word [pronunciation] → {target_language}>\n'
    f'  - <... 2-5 items total, one bullet per line>'
)
```

The rubric is joined with `\n\n`, so the new block stays its own
paragraph in the prompt — no other rubric changes needed.
`_insert_blank_before_lists()` (`tutor/markdown_util.py:25`) already
injects the blank line python-markdown needs between
`📚 Vocabulary:` and the first `- …`, so the streaming path in
`tutor/web_sink.py:142` produces a clean `<ul>` on every chunk too.

## Files modified

- `tutor/prompts.py` — vocabulary row in the rubric.
- `tests/test_prompts.py` — new regression test
  `test_build_base_system_prompt_vocabulary_template_is_bulleted`
  that walks the prompt, locates the Vocabulary block, and asserts it
  contains at least two `- ` bullet lines and the `2-5 items` count.

## Verification

1. `make lint` and `uv run --frozen pytest tests/test_prompts.py
   tests/test_markdown_util.py`.
2. Run the app, trigger Explain on a line in each supported source
   language (Japanese, Chinese, Korean, non-CJK), and confirm the
   Vocabulary section renders as a `<ul>` with 2-5 `<li>` items both
   while streaming and after the final chunk.
3. Spot-check at `beginner`, `intermediate`, and `advanced` levels.
