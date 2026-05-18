# Japanese: show kyūjitai forms in explanations

## Context

The base system prompt in `tutor/prompts.py` (`build_base_system_prompt`)
already emits a `🔁 Variant:` row for Chinese that rewrites the raw line
in the other script (simplified ↔ traditional), and uses a dual-script
vocabulary format `学习 / 學習 (xuéxí, [ɕɥěɕǐ]) → 학습`. A Japanese learner
reading modern subtitles (shinjitai / 新字体) gets no analogous help
recognising the older kyūjitai (旧字体) forms they will encounter in
literature, older signage, names, and adjacent Taiwanese/HK text. The
Chinese feature was added in commit `405aadb` and made mandatory in
`3054dc5`; this change ports the same shape to Japanese.

Like the Chinese feature, this is purely a system-prompt change —
storage, web rendering, and the explain pipeline are script-agnostic.

## Approach

Two edits inside `build_base_system_prompt` in `tutor/prompts.py`:

1. **Generalize the `🔁 Variant:` row** so it covers both Chinese and
   Japanese. ALWAYS include when source is Chinese (existing invariant
   kept). Include for Japanese whenever the line contains at least one
   kanji with a kyūjitai variant. Omit only when neither condition
   holds. The override of the "skip any empty section" rule that
   protects the Chinese row is extended to the Japanese case.

2. **Extend the Japanese pronunciation/vocabulary bullet** to show both
   forms when applicable, parallel to the Mandarin bullet. Format:
   `新字体 / 旧字体 (hiragana, [IPA]) → translation`; drop the slash and
   second form when no kanji in the word has a kyūjitai variant.
   Examples: `学校 / 學校 (がっこう, [ɡakkoː]) → 학교` and the existing
   `受け入れる (うけいれる, [ɯke̞iɾe̞ɾɯ]) → 받아들이다` (no kyūjitai applies).

The 100-word explanation budget is unaffected: the Variant row is one
rewritten line, vocab items pick up at most a handful of characters.

## Exact edits

`tutor/prompts.py`, inside `build_base_system_prompt`:

- Replace the Variant row instruction with the generalized wording that
  names both Chinese and Japanese conditions and re-asserts the
  skip-empty override.
- Replace the Japanese pronunciation bullet with a dual-form variant
  that mirrors the Mandarin "show both scripts" bullet, keeping the
  existing no-kyūjitai example as the second illustration.

## Critical files

- `tutor/prompts.py` — the only code change.
- `tests/test_prompts.py`:
  - New `test_build_base_system_prompt_mentions_japanese_kyujitai`
    asserts `'kyūjitai'`, `'旧字体'`, and `'学校 / 學校'` appear.
  - New `test_build_base_system_prompt_japanese_variant_conditions`
    asserts both the Chinese ALWAYS clause and the Japanese clause are
    present, and that the skip-empty override remains.
  - The existing `..._chinese_variant_is_mandatory` and
    `..._separates_sections_with_blank_lines` tests are updated to the
    new wording (`'ALWAYS include when the source is Chinese'`).
  - `..._includes_ipa_for_every_language` is unchanged — the
    `(うけいれる, [ɯke̞iɾe̞ɾɯ])` example survives as the no-kyūjitai case.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test:
   - Launch the app, ingest a Japanese subtitle, set
     `Learning = Japanese`, `Native = Korean`, `Level = intermediate`.
   - Click Explain on lines with kyūjitai-bearing kanji (学, 国, 体, 当,
     関, 経, 会, …): confirm the `🔁 Variant:` row appears with the
     kyūjitai rewrite, and that at least one vocabulary item uses the
     `新字体 / 旧字体` form.
   - Click Explain on a line with no kyūjitai-variant kanji
     (hiragana/katakana only, or 人/山/川 only): confirm the Variant row
     is omitted and vocabulary uses the no-slash form.
   - Sanity: a Chinese subtitle still shows simplified ↔ traditional
     Variant; an English/Korean subtitle still shows no Variant row.
