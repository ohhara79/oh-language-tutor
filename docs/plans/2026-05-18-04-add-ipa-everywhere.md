# Add IPA alongside every pronunciation aid

## Context

The base system prompt (`tutor/prompts.py`, `build_base_system_prompt`) carved
the world into three buckets:

1. spelling-diverges languages (English, French, Russian, Arabic, Thai) — IPA;
2. Chinese / Japanese — pinyin or hiragana **explicitly "not IPA"**;
3. phonetic-script source languages (Korean Hangul, Spanish, Italian,
   Indonesian) — omit pronunciation entirely.

Pinyin, hiragana, and "phonetic" scripts each have allophonic or assimilation
edges the romanization or script alone doesn't disambiguate — e.g. pinyin
`shi` / `xi` / `zi` share the letter `i` but cover three different vowels,
Japanese `ん` realizes differently before different consonants, Korean
batchim assimilates across morpheme boundaries, Spanish stress isn't always
written. A learner who wants to know what a word *sounds* like has no signal
in the explanation for buckets 2 and 3.

Add an IPA transcription to every vocabulary entry, alongside the existing
language-specific aid (pinyin / hiragana) when one applies. No data model,
no UI, no LLM-call changes — the entire feature lives in the system prompt.

## Approach

Single-file change in `tutor/prompts.py`, function `build_base_system_prompt`
(lines 52–65, the `'Pronunciation notation:'` block). Rewrite so:

- **Always** include IPA in square brackets.
- When a language-specific aid (pinyin, hiragana) applies, place it **before**
  the IPA inside the same parenthesis group, comma-separated.
- For source languages whose script is already phonetic (Korean Hangul,
  Spanish, Italian, Indonesian, …), keep the IPA in brackets — no other aid.
- For languages already using IPA only (English, French, Russian, Arabic,
  Thai, …), nothing changes.

The Chinese dual-script rule from `2026-05-18-03` is preserved: drop the `/`
and second form when the two scripts are identical for that word.

### Target examples (these go into the prompt)

```
accept [əkˈsɛpt] → 받아들이다
受け入れる (うけいれる, [ɯke̞iɾe̞ɾɯ]) → 받아들이다
学习 / 學習 (xuéxí, [ɕɥěɕǐ]) → 학습
你好 (nǐ hǎo, [ni˨˩˦ xɑʊ̯˨˩˦]) → 안녕하세요
안녕하세요 [annjʌŋɦasejo] → 안녕하세요
```

## Exact edits

`tutor/prompts.py`, inside `build_base_system_prompt`, replace the
`'Pronunciation notation:'` block (lines 52–65) with the unified rules above.
Add `# noqa: RUF001` to source lines that contain ambiguous-unicode IPA
characters (carons, tone letters, combining diacritics, primary-stress mark).

No other files in `tutor/` need changing — `build_explain_user_message`, the
thread prompt, storage layer, and web/UI templates are all script-agnostic.

## Tests

`tests/test_prompts.py` — add `test_build_base_system_prompt_includes_ipa_for_every_language`
asserting that:

- `(xuéxí, [ɕɥěɕǐ])` appears (Chinese pinyin + IPA in one parens),
- `(うけいれる, [ɯke̞iɾe̞ɾɯ])` appears (Japanese hiragana + IPA),
- `[annjʌŋɦasejo]` appears (phonetic-script language carries IPA),
- The strings `'not IPA'` and `'omit the bracket'` are gone, so a future
  edit can't silently reintroduce the carve-outs.

The new content is well under `MAX_SYSTEM_PROMPT_BYTES`; size-cap tests stay
green.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all existing tests plus
   the new one pass.
2. `make lint` — basedpyright + ruff clean.
3. Manual smoke test:
   - Start the web mode and paste a small mixed-language dataset, e.g. `学习`,
     `受け入れる`, `안녕하세요`, `accept`, `hola`.
   - Click Explain on each. Confirm the Vocabulary section shows IPA in
     brackets for every entry, with pinyin / hiragana preserved before the
     IPA for Chinese / Japanese.
   - Confirm previously phonetic-only languages (Korean, Spanish) now show
     IPA.
4. Spot-check tone rendering for Chinese — Chao tone letters
   (`˥ ˧˥ ˨˩˦ ˥˩`) should display correctly in the browser font. If the
   model produces caron-style diacritics on IPA vowels instead
   (`[ɕɥěɕǐ]`), that is also acceptable and conveys the same tone
   information.

## Critical files

- `tutor/prompts.py:52-65` — the only code change.
- `tests/test_prompts.py` — one new test.
