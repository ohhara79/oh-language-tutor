# Korean hanja variant: convert only when confident

## Context

Commit `62b0a45` (`docs/plans/2026-05-18-15-korean-hanja-variant.md`)
added a Korean Variant row driven purely by the LLM:
`build_base_system_prompt()` in `tutor/prompts.py` tells the model to
rewrite Sino-Korean (漢字語) words in hanja (漢字) while leaving
particles, endings, and native Korean words in Hangul.

In practice the model sometimes emits the wrong hanja — typically
because the line lacks enough context to disambiguate a homophone
(사기 = 詐欺 / 士氣 / 史記), pin down a proper noun, decide whether a
word is Sino-Korean or native, or pick a hanja the learner would
actually recognise. A wrong hanja is worse than no hanja for a
learner: it teaches the wrong form.

The fix is a prompt-only tightening at the **word level**: convert
only when confident, otherwise leave the word in Hangul. Partial
conversion (mixed Hangul / hanja) is fine — mixed script is the
traditional Korean convention — so the model never has to choose
between "guess" and "omit the whole row". The same rule extends to
Vocabulary entries: when the hanja form is uncertain, drop the slash
half and present the item as Hangul-only with IPA in brackets.

## Approach

Two edits inside `build_base_system_prompt()` in `tutor/prompts.py`.
No code outside this function changes; no new files.

1. **Variant row Korean clause** — replace the single-sentence
   "rewrite Sino-Korean words in hanja" instruction with a
   confidence-gated rule that lists four concrete don'ts:
   - proper noun without pinned context,
   - ambiguous homophone (e.g. 사기 = 詐欺 / 士氣 / 史記, 수도 =
     首都 / 水道 / 修道),
   - unclear whether the word is Sino-Korean or native (고유어),
   - rare or literary hanja a learner wouldn't recognise.

   The clause makes explicit that mixed Hangul/hanja is **preferred**
   over a wrong hanja, and that the whole row is omitted only when
   nothing converts confidently.

2. **Korean pronunciation bullet** — mirror the confidence gate in
   the vocab format. Sino-Korean items use `한글 / 漢字 (MR, [IPA])`
   only when the hanja is confident; otherwise they drop the slash
   form and become Hangul-only with IPA in brackets, like native
   Korean items. A new example `사기 [sʌːɡi] → fraud` illustrates the
   uncertain-Sino-Korean fallback.

The `🔁 Variant:` row's existing "skip any empty section rule does
not apply to this row" override is preserved.

## Critical files

- `tutor/prompts.py` — only edits to `build_base_system_prompt()`:
  - Variant row Korean clause.
  - Korean pronunciation bullet.
- `tests/test_prompts.py`:
  - New `test_build_base_system_prompt_korean_variant_confidence_rule`
    asserts the `Convert a word ONLY when you are confident` phrasing
    and each of the four don'ts (proper noun, homophone, native-vs-
    Sino unclear, rare / literary) appears verbatim.
  - New `test_build_base_system_prompt_korean_partial_conversion_allowed`
    asserts the `mixed Hangul / hanja`-is-PREFERRED phrasing and the
    "omit only when no word can be converted" rule.
  - New `test_build_base_system_prompt_korean_uncertain_vocab_drops_slash`
    asserts the uncertain-Sino-Korean vocab fallback example
    (`사기 [sʌːɡi]`) appears in the Korean pronunciation bullet.
  - Existing `..._korean_variant_omit_rule` is updated: the omit
    threshold is now phrased in terms of confidence rather than the
    presence of Sino-Korean words.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test on a Korean subtitle dataset:
   - Unambiguous Sino-Korean line (`학교에 갑니다.`) → expect
     `學校에 갑니다.` (unchanged behavior).
   - Ambiguous homophone in isolation (`사기가 떨어졌다.`) → expect
     `사기` to stay in Hangul rather than guess between 詐欺 / 士氣 /
     史記.
   - Proper noun without strong context (`민수가 왔어요.`) → expect
     the name to stay in Hangul.
   - Purely native line (`안녕하세요.`) → Variant row omitted, same
     as before.
   - Mixed line → expect partial conversion (confident words become
     hanja, uncertain words stay Hangul).
   - Vocab regression: a Sino-Korean item whose hanja the model
     can't confidently identify should appear as `한글 [IPA] →
     translation` rather than `한글 / 漢字 (MR, [IPA])`.
4. Sanity: Chinese and Japanese Variant rows still produce their
   existing dual-script outputs.

## Open / deferred questions

- **Lookup-table Phase 2**: if the model still hallucinates after
  this prompt tightening, a curated `hangul_hanja.json` table
  (mirroring `shinjitai_kyujitai.json`) would let us emit `[A|B|C]`
  brackets for ambiguous syllables and force the LLM to pick from a
  closed set. Out of scope here; defer until we see field results.
