# Always show the Variant row for Japanese and Chinese

## Context

For Japanese and Chinese explanations, the 🔁 Variant row is where the user
sees the pronunciation aids: furigana on kanji (Japanese) and pinyin on Han
characters (Chinese). Without that row, the explanation has no pronunciation
ruby anywhere — the Vocabulary row only covers 2–3 picked items.

Right now the row drops out in two situations:

1. **Japanese with no kyūjitai conversion.** `tutor/prompts.py:56-58` tells
   the model "When no GROUND TRUTH block is supplied, the source is Japanese
   but the line has no convertible kanji — omit the row." This fires whenever
   the kyūjitai lookup table has no entry for any of the line's kanji — but
   those kanji still benefit from furigana.
2. **Chinese where simplified == traditional.** `tutor/prompts.py:46-51`
   already says "ALWAYS include... even if most characters coincide", yet the
   model still drops the row when both scripts come out identical. The
   top-level "skip any empty section" rule (`prompts.py:40`) and the
   "NEVER emit two halves that are character-for-character identical" rule
   (`prompts.py:157-165`) give it cover to do so. Korean has an explicit
   "The 'skip any empty section' rule does not apply to this row"
   counter-clause (`prompts.py:85-87`); Japanese and Chinese do not.

The fix is prompt-only: rewrite the Japanese and Chinese halves of the Variant
clause so the row fires whenever the line has any character that can carry
ruby pronunciation (kanji for Japanese, Han characters for Chinese), and
extend the "skip any empty section does not apply" override to cover both
languages.

## Approach

Edit the Variant clause in `build_base_system_prompt`
(`tutor/prompts.py:46-88`) so that:

- **Chinese half (lines 46-51):** Keep "ALWAYS include". Add an explicit
  carve-out: even when simplified and traditional are character-for-character
  identical, still emit the row with per-character pinyin ruby — the row is
  the only place pinyin appears for the full line, so identical scripts is
  not a reason to skip. Note that the "NEVER emit two halves identical"
  Vocabulary rule (`prompts.py:157-165`) does not apply here because the
  Variant row emits a single rewrite, not a dual-form pair.

- **Japanese half (lines 51-58):** Replace the "omit the row when no
  convertible kanji" sentence with: when no GROUND TRUTH block is supplied
  but the line still contains kanji, copy the original line verbatim and
  wrap each kanji-bearing word in whole-word `<ruby>` furigana per the
  pronunciation rule. Only omit the row when the line has zero kanji
  (pure kana / ASCII), since there is nothing for furigana to attach to.

- **"skip any empty section" override:** Currently scoped to the Korean
  paragraph only (`prompts.py:85-87`). Lift it so it applies to the entire
  Variant row — Japanese and Chinese inherit the same protection. The
  cleanest spot is the leading rubric of the Variant clause: state that the
  row's omission conditions are the per-language rules above, and the
  generic "skip any empty section" rule does not apply.

The pronunciation rules at `prompts.py:104-138` already handle the ruby
markup; no changes needed there. No client-side or rendering changes —
`tutor/templates/partials/line.html:1-52` already renders whatever markdown
the model emits.

## Files

- `tutor/prompts.py` — rewrite the Variant clause inside
  `build_base_system_prompt` (single string literal at lines 46-88).
- `tests/test_prompts.py` — update / add assertions:
  - `test_build_base_system_prompt_japanese_variant_conditions`
    (lines 89-95): replace the assertion that hinges on the old
    "omit the row when no convertible kanji" wording. Add an assertion that
    the no-GROUND-TRUTH path still requires emitting the line with furigana.
  - `test_build_base_system_prompt_chinese_variant_is_mandatory`
    (lines 42-47): extend with an assertion that the "skip any empty
    section" rule is explicitly disclaimed for the Chinese variant.
  - New test: assert the Variant row carries a single "skip-empty does not
    apply" clause that covers Japanese and Chinese, not just Korean.

## Verification

1. `make lint` — basedpyright + ruff stay clean.
2. `uv run --frozen pytest tests/test_prompts.py` — all prompt invariants
   hold, including the new assertions.
3. Manual smoke via the running app:
   - Japanese line containing kanji whose readings have no kyūjitai
     variants (e.g. a sentence built from 食べる, 行く, 来る). The Variant
     row must render with furigana on each kanji-bearing word.
   - Japanese line that is pure hiragana (e.g. ありがとう). The Variant
     row should still be omitted — no kanji means no furigana.
   - Chinese line where simplified and traditional coincide
     (e.g. 你好). The Variant row must render with per-character pinyin
     ruby even though the characters match the original.
   - Korean and other languages unaffected — spot-check that their Variant
     behavior is unchanged.
