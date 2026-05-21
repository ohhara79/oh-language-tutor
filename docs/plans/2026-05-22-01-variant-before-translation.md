# Explanation section order: Variant before Translation

## Context

The Explanation rubric in the system prompt currently emits sections in this order: Translation → Variant → Vocabulary → Expression → Context. Variant is conditional and only appears for CJK source languages (Chinese / Japanese / Korean).

We want to swap Translation and Variant so that, when Variant is present, it appears first. Rationale: Variant is a transformation of the source line (script rewrite with ruby annotations), so grouping it adjacent to the original target line — before the meaning-side sections — reads more naturally for CJK learners. For non-CJK source languages, Translation remains the leading row (Variant is omitted entirely, so nothing changes for them).

New order:
1. Variant (CJK only)
2. Translation
3. Vocabulary
4. Expression
5. Context

## Change

### `tutor/prompts.py` — `build_base_system_prompt` (lines 299–312)

Reorder the `rows` list so Variant is appended first (when present), Translation second. Concretely, the current snippet that starts the list with Translation and then conditionally inserts Variant becomes: start with an empty list, append Variant if non-None, then append Translation, then Vocabulary / Expression / Context (unchanged).

The joining logic at line 313 (`'\n' + '\n\n'.join(rows) + '\n\n'`) is untouched — it still gives the leading row a single `\n` prefix and every subsequent row a `\n\n` prefix.

### `tests/test_prompts.py` — `test_build_base_system_prompt_separates_sections_with_blank_lines` (lines 164–183)

The test uses `build_base_system_prompt('Chinese', 'Korean', 'intermediate')`, where Variant is present and therefore becomes the new leading row. Update the labels tuple it iterates over to drop `Variant:` and add `Translation:`. Concretely the tuple becomes:

```python
('\U0001f3af Translation:', '\U0001f4da Vocabulary:', '\U0001f4a1 Expression:', '\U0001f3ac Context:')
```

The rest of the assertions (blank-line rule advertised, Chinese variant rule mentioned, "skip any empty section", "under 100 words") stay.

No other test in `tests/test_prompts.py` depends on Translation-vs-Variant ordering — the remaining tests find Variant via `prompt.index('\U0001f501 Variant:')` and inspect its clause text, which is independent of position.

## Out of scope

- No template/render changes: `tutor/markdown_util.py` and `tutor/templates/partials/line.html` preserve whatever order the LLM emits.
- No prompt copy changes beyond the rubric row order (the explanatory header on lines 284–297 doesn't list section names in order).
- Non-CJK behavior is unchanged: with no Variant row, Translation remains the leading row.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py` — all prompt tests pass, including the updated section-order test.
2. `make lint` — no type/lint regressions.
3. Spot-check by printing the prompt for a CJK source (e.g. Korean → English) and a non-CJK source (e.g. Spanish → Korean):
   - CJK: Variant appears before Translation; both are separated by a blank line.
   - non-CJK: Translation is still the first rubric row.
4. End-to-end sanity: run the app on a Korean line and confirm the rendered Explanation HTML shows Variant paragraph above Translation paragraph.
