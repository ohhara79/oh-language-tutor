# Korean Variant Ruby — Hanja Always as Base

## Context

The Variant row for Korean produces `<ruby>` annotations in the wrong
orientation. For the bug report:

- Input:    `그럼, 우울한 기를 즐겨`
- Got:      `그럼, <ruby>우<rt>憂</rt>울<rt>鬱</rt></ruby>한 <ruby>기<rt>氣</rt></ruby>를 즐겨`
- Wanted:   `그럼, <ruby>憂<rt>우</rt>鬱<rt>울</rt></ruby>한 <ruby>氣<rt>기</rt></ruby>를 즐겨`

The user wants **Hanja as the visible base text and Hangul as the small
`<rt>` ruby annotation in every Korean Variant ruby**, regardless of which
script the input line used.

The current clause (`tutor/prompts.py` `_VARIANT_CLAUSE_KOREAN`, lines
66–119) has two cases:

- (1) Hanja input → rewrite the line in Hangul, with Hanja as `<rt>`.
- (2) Hangul input → rewrite Sino-Korean words to Hanja, with Hangul as `<rt>`.

Case (2)'s ruby is already Hanja-base/Hangul-ruby — but the LLM is
inverting it anyway, because the case-split worked example for case (1)
(`<ruby>공<rt>工</rt>夫<rt>부</rt></ruby>`) hands the model a Hangul-base
template that it generalises in the wrong direction. The user has
confirmed that the right fix is to collapse the two cases into one
symmetric rule: **always Hanja base, always Hangul `<rt>`**.

## Approach

Unify the clause under one rule, applied per Sino-Korean span:

- **Hangul span in input** → convert it to its Hanja form in the
  rewrite, wrap as `<ruby>HANJA<rt>HANGUL-from-input</rt></ruby>`.
- **Hanja span in input** → KEEP the Hanja in the rewrite (no script
  conversion to Hangul), wrap as
  `<ruby>HANJA<rt>HANGUL-reading-from-context</rt></ruby>`. The
  variant line for a pure-Hanja sentence ends up character-for-character
  identical to the input apart from the ruby markup — the row's job is
  now the pronunciation reading.
- **Mixed input** → same rule per span.

All existing don'ts and judgement gates carry over verbatim:

- Multi-reading Hanja disambiguation (`樂 = 락/낙/요/악`, `行`, `不`, `北`,
  positive examples `音樂 → 음악`, `銀行 → 은행`, etc.). "Leave Hanja bare"
  escape becomes: skip the `<rt>` (or leave the word un-rubied) when no
  reading is contextually confident, instead of guessing.
- Hangul→Hanja confidence gate (a/b/c/d list — proper nouns, ambiguous
  homophones with the `사기` / `수도` positive examples and "go ahead
  and convert", Sino-vs-native uncertainty, rare/literary hanja).
- Particles (조사) and verb/adjective endings stay in Hangul, never
  inside `<ruby>`.
- Mixed Hangul/hanja partial conversion is PREFERRED over a wrong
  character.
- NEVER wrap spans that already match the input, particles, endings, or
  native Korean (고유어) words.
- Add: **NEVER put Hangul as the base or Hanja inside `<rt>`** — the
  orientation is fixed.
- Omit the row only when no word in the line can be converted with
  confidence; the "skip any empty section" override still does not
  apply.

### Worked examples in the prompt

Both examples now end up Hanja-base/Hangul-ruby. The second example's
purpose shifts to showing that Hanja input is **kept** rather than
rewritten:

- `input 공부합니다 → variant <ruby>工<rt>공</rt>夫<rt>부</rt></ruby>합니다`
  (Hangul input — line gains Hanja.)
- `input 工夫합니다 → variant <ruby>工<rt>공</rt>夫<rt>부</rt></ruby>합니다`
  (Hanja input — line keeps Hanja; ruby supplies the Hangul reading.)

## Files to touch

### `tutor/prompts.py`

Rewrite `_VARIANT_CLAUSE_KOREAN` (lines 66–119). High-level shape:

1. Open with the unified ruby orientation rule (Hanja base, Hangul
   `<rt>`, one Hanja per `<rt>`, one outer `<ruby>` per Sino-Korean
   word, one-hanja-equals-one-syllable alignment).
2. Per-span behaviour: Hangul Sino-Korean → convert to Hanja; Hanja →
   keep, supply Hangul reading.
3. Reuse the multi-reading disambiguation paragraph (with `樂`/`行`/`不`/`北`
   examples and positive cases) reframed to "picking the Hangul reading".
4. Reuse the confidence-gate paragraph (a/b/c/d + homophone examples)
   verbatim for the Hangul→Hanja conversion direction.
5. Reuse the "particles and endings stay in Hangul" / partial-conversion
   PREFERRED / never-wrap-particles-or-고유어 sentences.
6. Two worked examples as listed above.
7. Reuse the omit clause: `no word in the line can be converted with
   confidence`; `does not apply to this row`.

The case (1) substantive instruction "rewrite the entire line in
Hangul" is dropped — its replacement is "keep Hanja, supply Hangul
reading as ruby". Wording must preserve the substrings the existing
tests rely on (see below).

### `tests/test_prompts.py`

- **`test_build_base_system_prompt_korean_variant_calls_for_ruby`
  (lines 256–274)** — drop `assert 'hanja ruby' in variant_clause`
  (line 270); the new prompt never says "hanja ruby" because Hanja is
  never `<rt>`. Keep `<ruby>`, `<rt>`, `one hanja = one Hangul syllable`,
  `Hangul ruby`, `NEVER wrap`, `고유어`. Add a positive orientation
  assertion (e.g. `'Hanja as base' in variant_clause` or whatever exact
  phrase the rewrite uses) so the unified rule is tested.

- **`test_build_base_system_prompt_korean_variant_ruby_worked_examples`
  (lines 277–284)** — replace the line-284 assertion
  (`<ruby>공<rt>工</rt>부<rt>夫</rt></ruby>`) with one that proves the
  Hanja-input case keeps Hanja-base, e.g.:
  `assert 'input 工夫합니다 → variant <ruby>工<rt>공</rt>夫<rt>부</rt></ruby>합니다' in prompt`.
  Keep the line-282 substring assertion. Update the docstring comment to
  drop the "two directions" framing.

- **`test_build_base_system_prompt_korean_variant_omit_rule`
  (lines 205–214)** — substrings `no word in the line can be converted
  with confidence`, `고유어`, `does not apply to this row` must survive
  the rewrite; confirm wording is preserved in lockstep.

- **`test_build_base_system_prompt_korean_partial_conversion_allowed`
  (lines 247–253)** — substrings `mixed Hangul / hanja`, `PREFERRED`,
  `Omit the entire row only when no word in the line can be converted`
  must survive.

- **`test_build_base_system_prompt_korean_variant_confidence_rule`
  (lines 225–244)** — all a/b/c/d assertions and the homophone /
  positive-conversion sentences must survive.

- **`test_build_base_system_prompt_mentions_korean_hanja_variant`
  (lines 195–202)** — substrings `hanja`, `漢字`, `漢字語`, `학습 / 學習`
  must survive. (`학습 / 學習` lives in the pronunciation bullet, not
  the Variant clause, so unaffected.)

### `docs/plans/2026-05-21-11-korean-variant-hanja-base-ruby.md` (new)

Plan file per `docs/rules/plans.md`: Context, Approach, Files to touch,
Verification. Do not edit `docs/plans/2026-05-21-08-korean-variant-ruby.md`
— prior plans are immutable history; this plan supersedes it.

## Edge cases

- **Pure-Hanja input with no confident readings** — omit the row (the
  confidence-based omit clause already covers this).
- **Mixed confident/uncertain Hanja within one word** — partial
  conversion is PREFERRED: rubify the confident Hanja, leave the
  uncertain one outside the `<ruby>` span.
- **Pure-Hangul input with no Sino-Korean words convertible** — omit
  the row (existing behaviour, preserved).
- **Multi-reading Hanja** (e.g. surname `金` vs. metal `김`) — falls
  under the existing disambiguation paragraph; the orientation is
  unchanged.

## Verification

- `make lint` clean.
- `uv run --frozen pytest tests/test_prompts.py` — Korean variant tests
  pass with the updated assertions.
- Manual: replay `그럼, 우울한 기를 즐겨` through the app; the Variant
  row must render with `憂鬱` and `氣` as the visible base and `우울` /
  `기` as the small ruby annotations.
- Manual: a Hanja-bearing input line (e.g. one containing `工夫` or
  `學習`) — the Variant row keeps the Hanja in place and supplies
  Hangul readings as `<rt>`; no Hanja appears inside `<rt>` anywhere
  in the row.
