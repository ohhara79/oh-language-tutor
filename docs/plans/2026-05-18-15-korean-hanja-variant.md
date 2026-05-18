# Korean: show hanja substitutions in explanations

## Context

The base system prompt in `tutor/prompts.py` (`build_base_system_prompt`)
already emits a `🔁 Variant:` row for Chinese (simplified ↔ traditional)
and Japanese (shinjitai → kyūjitai), with a dual-script vocabulary
format such as `学习 / 學習 (xuéxí, [ɕɥěɕǐ]) → 학습` and
`学校 / 學校 (がっこう, [ɡakkoː]) → 학교`. A Korean learner reading modern
Hangul subtitles gets no analogous help recognising the hanja (漢字)
forms they will meet in news, legal text, names, and academic writing.

The Chinese feature relies purely on LLM knowledge (no lookup table);
Japanese pre-computes a kyūjitai template from
`tutor/data/shinjitai_kyujitai.json`. Korean hangul → hanja is highly
ambiguous at the syllable level but the ambiguity collapses at the
word level once the model knows the sentence meaning, so a lookup
table buys little; we follow the Chinese pattern.

Like the Chinese feature, this is purely a system-prompt change —
storage, web rendering, and the explain pipeline are script-agnostic
and need no edits.

## Approach

Two edits inside `build_base_system_prompt` in `tutor/prompts.py`:

1. **Extend the `🔁 Variant:` row** with a "For Korean" clause:
   rewrite Sino-Korean (漢字語) words in hanja (漢字); particles (조사),
   verb/adjective endings, and native Korean (고유어) words stay in
   Hangul. Pick the hanja form whose meaning fits the line in context
   (e.g. 사기 → 詐欺 / 士氣 / 史記). Omit the row when the line has no
   Sino-Korean words. The override of the "skip any empty section"
   rule that protects the Chinese and Japanese rows is extended to
   the Korean case.

2. **Add a dedicated Korean pronunciation bullet** between the
   Mandarin bullet and the catch-all phonetic-script bullet:
   `한글 / 漢字 (McCune-Reischauer, [IPA]) → translation` for
   Sino-Korean words, e.g. `학습 / 學習 (haksŭp, [haks͈ɯp]) → study`.
   Drop the slash and second form for native Korean words and use
   brackets-only since Hangul is phonetic, e.g.
   `아름답다 [a̠ɾɯmda̠p̚t͈a̠] → beautiful`. The catch-all phonetic-script
   bullet loses "Korean Hangul" from its list (now redundant) and
   uses Spanish `hola [ˈola] → 안녕` as its illustration.

The 100-word explanation budget is unaffected.

## Exact edits

`tutor/prompts.py`, inside `build_base_system_prompt`:

- Append a "For Korean:" clause to the Variant row instruction,
  parallel to the Chinese and Japanese clauses already on that row.
- Insert a dedicated Korean pronunciation bullet between the Mandarin
  and catch-all bullets, with the dual-script Sino-Korean example and
  the brackets-only native-Korean example.
- Update the catch-all phonetic-script bullet to drop "Korean Hangul"
  and use a Spanish IPA example instead.

## Critical files

- `tutor/prompts.py` — the only code change.
- `tests/test_prompts.py`:
  - New `test_build_base_system_prompt_mentions_korean_hanja_variant`
    asserts `'hanja'`, `'漢字'`, `'漢字語'`, and `'학습 / 學習'` appear.
  - New `test_build_base_system_prompt_korean_variant_omit_rule`
    asserts the no-Sino-Korean-words omit rule, the 고유어 callout,
    and the skip-empty override are all present.
  - New `test_build_base_system_prompt_korean_dual_script_vocab_format`
    asserts the `학습 / 學習 (haksŭp, [haks͈ɯp])` and `아름답다
    [a̠ɾɯmda̠p̚t͈a̠]` examples appear verbatim.
  - `..._includes_ipa_for_every_language` is updated: the Hangul
    example moves to the new Korean bullet, and the catch-all
    illustration becomes `[ˈola]` (Spanish).

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test:
   - Launch the app, ingest a Korean subtitle, set
     `Learning = Korean`, `Native = English`, `Level = intermediate`.
   - Click Explain on lines with Sino-Korean words (e.g.
     `한국어를 공부해요.`, `학교에 갑니다.`): confirm the `🔁 Variant:` row
     appears with the hanja rewrite (e.g. `韓國語를 工夫해요.`,
     `學校에 갑니다.`), and that at least one vocabulary item uses the
     `한글 / 漢字` form.
   - Click Explain on a purely native line (e.g. `안녕하세요.`,
     `아름답다.`): confirm the Variant row is omitted and vocabulary
     uses the no-slash brackets-only form.
   - Click Explain on a mixed line: confirm only Sino-Korean tokens
     receive hanja and that 조사 / endings stay in Hangul.
   - Sanity: a Chinese subtitle still shows simplified ↔ traditional
     Variant; a Japanese subtitle still shows the kyūjitai Variant;
     an English subtitle still shows no Variant row.
