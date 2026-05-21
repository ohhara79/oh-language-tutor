# Korean Vocab / Variant Hanja — Cross-Row Consistency

## Context

In Korean output, the vocabulary row sometimes emits a Sino-Korean
headword in the dual-script `한글 / 漢字` form while the same word
appears in the Variant row as plain Hangul (no `<ruby>`, no hanja).
That is internally inconsistent: dual-scripting in vocab is a positive
confidence signal that the model knows the word's hanja form, so the
Variant row should rubify it; conversely, leaving a word as plain
Hangul in the Variant row signals "hanja uncertain," so the vocab row
should drop the slash.

The two rows live in separate clauses today:

- `_VARIANT_CLAUSE_KOREAN` (`tutor/prompts.py`, lines 66–135) gates
  ruby with its own confidence list (proper nouns, ambiguous
  homophones, native-vs-Sino-Korean, rare/literary hanja) and an
  atomicity rule.
- `_PRONUNCIATION_BULLET_KOREAN` (`tutor/prompts.py`, lines 201–220)
  gates dual-script with "same don'ts as the Variant row above" plus
  positive examples (`학습 / 學習`, `工夫 / 공부`).

Both clauses say "use the same don'ts," but neither says the two
decisions must AGREE for the same word. The model can pass both gates
independently and emit a row pair that contradicts itself. Make the
agreement explicit.

## Approach

Add one cross-row consistency rule to `_PRONUNCIATION_BULLET_KOREAN`
(the natural home — it already references the variant row's don'ts)
and a short mirror reminder inside `_VARIANT_CLAUSE_KOREAN` so a model
reading just the variant clause also sees the constraint.

Rule, in plain terms:

- If a Sino-Korean word is shown in vocab as `한글 / 漢字`, the same
  word must appear in the Variant row wrapped as
  `<ruby>漢字<rt>한글</rt></ruby>` using **the same hanja characters**.
- If a Sino-Korean word is left as plain Hangul (un-rubied) in the
  Variant row, the vocab row must drop the slash and emit Hangul only
  for that word.
- Per word: one word being dual-script/rubified while another is plain
  Hangul on the same line is fine; mixing the two states for the
  *same* word is forbidden.

## Files to touch

### `tutor/prompts.py`

- **`_PRONUNCIATION_BULLET_KOREAN`** (lines 201–220): append a new
  sub-bullet at the end stating the cross-row consistency rule.
- **`_VARIANT_CLAUSE_KOREAN`** (lines 66–135): insert a one-sentence
  cross-reference near the per-word atomicity sentence so a reader of
  just the variant clause also sees the rule.

### `tests/test_prompts.py`

Add `test_build_base_system_prompt_korean_vocab_variant_consistency`
asserting the consistency phrasing lives in the pronunciation bullet
and the cross-reference lives in the variant clause.

### `docs/plans/2026-05-21-13-korean-vocab-variant-consistency.md` (this file)

Per `docs/rules/plans.md`: `NN = 13` (next after `12`). Do not edit
prior plan files.

## Edge cases

- **Confidence carve-outs (proper nouns, ambiguous homophones,
  native-vs-Sino, rare/literary).** Unchanged — they determine whether
  *either* row uses hanja. The new rule ties the row-level decisions
  together: whatever the carve-out concludes, both rows honour it
  identically.
- **Same Hangul reading, different hanja in vocab vs. variant.**
  Forbidden by the "same hanja characters" clause.
- **Vocab compound vs. variant phrase.** The compound's hanja choice
  and ruby alignment must match what vocab shows.
- **Native Korean (고유어) vocab.** Already drops the slash; variant
  already leaves un-rubied. Consistent by construction; no new
  behaviour.

## Verification

- `make lint` clean.
- `uv run --frozen pytest tests/test_prompts.py` — new test passes,
  existing Korean tests still pass.
- Manual: replay a Korean line whose vocab row shows `Hangul / Hanja`
  for a word that the Variant row leaves plain. After the change,
  either both rows show hanja with matching characters or both leave
  the word in Hangul.
