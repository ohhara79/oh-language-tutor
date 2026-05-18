# CJK vocab: never emit `X / X` duplicate dual-script halves

## Context

For Japanese, Mandarin Chinese, and Korean source languages, the
Explain output's vocabulary items use a dual-script format separated
by " / " (新字体 / 旧字体, simplified / traditional, Hangul / 漢字).
Each language bullet in the `Pronunciation notation` section of
`build_base_system_prompt()` (`tutor/prompts.py`) has a conditional
"Drop the slash and second form when …" instruction:

- Japanese: drop when no kanji has a kyūjitai variant per GROUND
  TRUTH.
- Mandarin: drop when the two scripts are identical for that word.
- Korean: drop when the word is native (고유어), or when the
  Sino-Korean hanja is uncertain.

In practice the model still sometimes emits identical-halves items
such as `受け入れる / 受け入れる`, `你好 / 你好`, or `학습 / 학습`. Each
per-language drop-condition is correct, but they're phrased as
*reasons* to drop rather than a flat ban on duplicates, and the
model occasionally pattern-matches on the dual-script habit and
forgets the conditional.

This change adds a single emphatic global rule that acts as a
backstop: regardless of which language's drop-condition fired (or
didn't), the model must never emit two halves that are
character-for-character identical.

## Approach

A single bullet inserted inside `build_base_system_prompt()` in
`tutor/prompts.py`, immediately after the Korean pronunciation bullet
and before the catch-all phonetic-script bullet:

> - Critical for every dual-script vocab item (Japanese 新字体 /
>   旧字体, Mandarin simplified / traditional, Korean Hangul / 漢字):
>   NEVER emit two halves that are character-for-character identical.
>   If the second form would equal the first exactly, drop the slash
>   and the duplicate and emit only the single form. This is a hard
>   rule that reinforces the per-language "drop the slash" conditions
>   above and catches any case they miss.

The three per-language drop-conditions stay — they still document the
*reason* to drop in normal cases. The new bullet is additive. The
Variant row is unaffected because it's a full sentence rewrite, not
a slash-separated pair, so the `X / X` shape can't occur there.

## Critical files

- `tutor/prompts.py` — single bullet insertion inside
  `build_base_system_prompt()` after the Korean pronunciation bullet.
- `tests/test_prompts.py`:
  - New `test_build_base_system_prompt_forbids_duplicate_dual_script`
    asserts the `NEVER emit two halves that are character-for-
    character identical` phrase, the explicit mention of all three
    dual-script pairings (`新字体 / 旧字体`, `simplified / traditional`,
    `Hangul / 漢字`), and the `drop the slash and the duplicate`
    action.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test:
   - Japanese line whose vocab includes a kanji-free word
     (e.g. 受け入れる) → expect single-form
     `受け入れる (うけいれる, [ɯke̞iɾe̞ɾɯ]) → …`, not
     `受け入れる / 受け入れる …`.
   - Mandarin line including a script-identical word (e.g. 你好) →
     expect `你好 (nǐ hǎo, [ni˨˩˦ xɑʊ̯˨˩˦]) → …`, not `你好 / 你好 …`.
   - Korean line with a native item (e.g. 아름답다) → expect
     `아름답다 [a̠ɾɯmda̠p̚t͈a̠] → …`, not `아름답다 / 아름답다 …`. A
     confident Sino-Korean item (e.g. 학습) should still appear as
     `학습 / 學習 (haksŭp, [haks͈ɯp]) → …` — the new rule only strips
     *duplicate* halves.
4. **Regression** — non-duplicate dual-script vocab examples in
   Chinese / Japanese / Korean still render normally; the Variant
   rows are unchanged.
