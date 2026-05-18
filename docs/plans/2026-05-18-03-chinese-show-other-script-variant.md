# Chinese: show the other script in explanations

## Context

The base system prompt (`tutor/prompts.py`, `build_base_system_prompt`) currently
gives Mandarin a single pronunciation rule:

> For Mandarin Chinese, use pinyin with tone marks in parentheses (not IPA),
> e.g. 接受 (jiēshòu) → 받아들이다.

That ignores the simplified/traditional split. A learner reading a simplified-
script subtitle stream cannot recognise the same words on a Taiwan/Hong Kong
sign, and vice versa. The fix is purely prompt-side: Claude already sees the
raw line and can tell which script it is in, so we just need to tell it to
emit the other form too.

## Approach

Single-file change in `tutor/prompts.py`, function `build_base_system_prompt`
(lines 24–68). Two adjustments:

1. **New `🔁 Variant:` row in the explanation structure** (lines 40–47),
   inserted between Translation and Vocabulary. It carries the raw line
   rewritten into the other Chinese script. Per the existing "skip any empty
   section" rule, Claude will omit it when (a) the source is not Chinese, or
   (b) the line contains no characters that differ between scripts.

2. **Extend the Mandarin Chinese bullet in "Pronunciation notation"**
   (line 55) so vocabulary items show both scripts as
   `学习 / 學習 (xuéxí) → 학습`, raw-script first. Add an explicit note that
   the slash and second form are dropped when the two scripts are identical
   for that word (e.g. `你好 (nǐ hǎo) → 안녕하세요`).

Word-budget note: the explanation structure already says "stay under 100
words". The Variant row is a single rewritten line, not new analysis, so it
fits comfortably; no change to the budget.

## Exact edits

`tutor/prompts.py`, inside `build_base_system_prompt`:

- After the Translation row (currently line 42), add:
  ```
  '  \U0001f501 Variant:     <raw line rewritten in the other Chinese '
  'script — simplified ↔ traditional; omit when source is not Chinese or '
  'the line is script-identical>\n'
  ```

- Replace the current Mandarin pronunciation bullet (lines 55–56):
  ```
  '- For Mandarin Chinese, use pinyin with tone marks in parentheses (not IPA),\n'
  '  e.g. 接受 (jiēshòu) → 받아들이다.\n'
  ```
  with:
  ```
  '- For Mandarin Chinese, show both scripts separated by " / " '
  '(raw-script first), with pinyin and tone marks in parentheses (not IPA),\n'
  '  e.g. 学习 / 學習 (xuéxí) → 학습.\n'
  '  Drop the slash and second form when the two scripts are identical '
  'for that word, e.g. 你好 (nǐ hǎo) → 안녕하세요.\n'
  ```

No other files need changing. `build_explain_user_message`, the thread prompt,
and the storage layer are all script-agnostic and require no work.

## Tests

`tests/test_prompts.py` — add one assertion to a new test that the rendered
base prompt contains the Variant row and the new dual-script vocabulary
example. The bytes of the new content are well under
`MAX_SYSTEM_PROMPT_BYTES`, so size-cap tests stay green.

```python
def test_build_base_system_prompt_mentions_chinese_variant() -> None:
    prompt = build_base_system_prompt('Mandarin Chinese', 'Korean', 'intermediate')
    assert 'Variant' in prompt
    assert '学习 / 學習' in prompt
```

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all existing tests
   plus the new one pass.
2. `make lint` — clean.
3. Manual smoke test:
   - Launch the app, point a Chinese stdin source at it, set
     `source_language = "Simplified Chinese"`, `target_language = "Korean"`.
   - Click Explain on a line containing characters that differ in traditional
     (e.g. anything with 学, 国, 时, 个, 们). Confirm the response shows the
     `🔁 Variant:` row with the traditional version, and that vocabulary
     items use the `学习 / 學習 (xuéxí) → 학습` format.
   - Repeat with `source_language = "Traditional Chinese"` on a traditional
     subtitle; confirm the variant row now shows simplified.
   - Sanity check: a Korean or English source still produces no Variant row
     (the skip-empty rule applies).

## Critical files

- `tutor/prompts.py:24-68` — the only code change.
- `tests/test_prompts.py` — add one test.
