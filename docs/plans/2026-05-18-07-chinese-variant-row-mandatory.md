# Force the Chinese Variant row to always render

## Context

Commit 405aadb ("Show the other Chinese script in explanations.") added a
`🔁 Variant:` row to the system prompt so that a learner reading
simplified-script subtitles sees each line rewritten in traditional, and
vice versa. In practice the row often does not appear: the model judges
the line "script-identical" or quietly drops the row under the "skip any
empty section" rule that governs the whole Explanation structure.

The cause is the Variant instruction itself in `tutor/prompts.py:43-45`,
which gives the model two ways out:

```
'  \U0001f501 Variant:     <raw line rewritten in the other Chinese '
'script — simplified ↔ traditional; omit when source is not Chinese '
'or the line is script-identical>\n'
```

Combined with `tutor/prompts.py:40` ("skip any empty section"), the model
treats the row as discretionary and frequently omits it — even on lines
that clearly differ across scripts.

## Approach

Prompt-only change. Replace the Variant instruction with wording that
keeps the non-Chinese carve-out but removes the script-identical carve-out
and explicitly overrides the skip-empty rule for this row.

## Exact edit

`tutor/prompts.py`, replace lines 43-45:

```python
'  \U0001f501 Variant:     <raw line rewritten in the other Chinese '
'script — simplified ↔ traditional; omit when source is not Chinese '
'or the line is script-identical>\n'
```

with:

```python
'  \U0001f501 Variant:     <raw line rewritten in the other Chinese '
'script — simplified ↔ traditional. ALWAYS include this row when the '
'source is Chinese, even if most characters coincide across scripts; '
'the "skip any empty section" rule does not apply here. Omit ONLY '
'when the source is not Chinese.>\n'
```

The Variant row is one rewritten line, so the 100-word explanation budget
is unaffected.

## Critical files

- `tutor/prompts.py:43-45` — the only code change.
- `tests/test_prompts.py` — add a sibling to
  `test_build_base_system_prompt_mentions_chinese_variant` that asserts
  the new mandatory phrasing is present and the `script-identical`
  carve-out is gone, so a future edit cannot silently reintroduce it.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test:
   - Launch the app, ingest a simplified-Chinese subtitle, set
     `Learning = Chinese`, `Native = Korean`, `Level = intermediate`.
   - Click Explain on several lines, including short ones whose
     characters mostly coincide across scripts. Confirm the `🔁 Variant:`
     row appears on every Chinese line.
   - Switch to a traditional-Chinese subtitle, confirm the Variant row
     now shows simplified.
   - Sanity check: a non-Chinese subtitle (English, Korean) still
     produces no Variant row.
