# Korean Variant Ruby — Forbid Half-Converted Words

## Context

Even after the unified "Hanja as base, Hangul as `<rt>`" rule
(`2026-05-21-11-korean-variant-hanja-base-ruby.md`, commit `89c798e`),
the Korean Variant row still produces broken ruby on multi-syllable
Sino-Korean words. Bug report:

- Input:  `지갑이 되고 싶다면? 아님, 모자가 되고 싶다면?`
- Got:    `<ruby>地<rt>지</rt></ruby>갑이 되고 싶다면? 아님, <ruby>帽<rt>모</rt><rt>자</rt></ruby>가 되고 싶다면?`

Two failure modes, both on one line:

1. **Half-conversion of a word.** `지갑` got a Hanja for `지` (the wrong
   one — `地` rather than `紙`) and `갑` was left as plain Hangul outside
   the `<ruby>`. The reader sees `地갑`, which is not a Korean word in
   any script.
2. **Hanja / `<rt>` count mismatch inside one `<ruby>`.** `모자` rendered
   as `<ruby>帽<rt>모</rt><rt>자</rt></ruby>` — one Hanja base, two
   `<rt>`. The second syllable's reading floats with no Hanja above it;
   `子` is missing entirely. The reader cannot tell which Hangul syllable
   maps to `帽`.

Both reduce to one root cause: the current clause endorses
"partial conversion (mixed Hangul / hanja) is PREFERRED over a wrong
character," but only intends that *between* words. The model is
generalising the permission *inside* a word — picking a Hanja for one
syllable and leaving the rest. The prompt never explicitly states that
a Sino-Korean word is converted **atomically**: either every syllable
becomes a Hanja + `<rt>` pair inside one outer `<ruby>`, or the whole
word stays in plain Hangul outside any `<ruby>`. The structural
invariant (Hanja count = `<rt>` count inside one `<ruby>`) is implicit
in "one hanja per `<rt>`" but the model is not honouring it.

The fix spells both rules out as hard prohibitions, with explicit
counter-examples so the model has a concrete template to avoid.

## Approach

Targeted additions to `_VARIANT_CLAUSE_KOREAN` in `tutor/prompts.py`;
no rewrite of the existing structure.

1. **Structural invariant inside `<ruby>`.** Inside one outer `<ruby>`,
   Hanja base characters and `<rt>` elements alternate one-to-one
   (`HANJA<rt>HANGUL</rt>HANJA<rt>HANGUL</rt>...`). The count of Hanja
   bases MUST equal the count of `<rt>` children. NEVER emit two
   consecutive `<rt>`s and NEVER emit a `<rt>` without a preceding
   Hanja base in the same `<ruby>`. Slotted right after the orientation
   sentence (`NEVER put Hangul as the base or hanja inside <rt>`).
2. **Per-word atomicity.** Confidence applies to the whole Sino-Korean
   word, not per syllable. Either every syllable of a Sino-Korean word
   is a Hanja + `<rt>` pair inside one outer `<ruby>`, or the entire
   word stays in plain Hangul outside any `<ruby>`. NEVER convert only
   part of a multi-syllable Sino-Korean word — the remaining Hangul
   syllables abutting the `<ruby>` form a non-word. The existing
   "mixed Hangul / hanja partial conversion is PREFERRED" sentence
   stays — clarified to apply at word granularity, not syllable
   granularity inside a word.
3. **Two negative worked examples** appended after the existing
   positive examples, prefixed with the literal `NEVER`:
   - `NEVER <ruby>地<rt>지</rt></ruby>갑` (half-converted word — either
     rubify both syllables or leave the whole word in Hangul).
   - `NEVER <ruby>帽<rt>모</rt><rt>자</rt></ruby>` (Hanja count must
     equal `<rt>` count — either `<ruby>帽<rt>모</rt>子<rt>자</rt></ruby>`
     when fully confident, or leave `모자` in Hangul).

The carve-outs (proper nouns, ambiguous homophones, native-vs-Sino,
rare/literary hanja) carry over verbatim — read with the new
atomicity rule, uncertainty about *any* syllable of a word leaves the
whole word un-rubied.

## Files to touch

### `tutor/prompts.py`

Edit `_VARIANT_CLAUSE_KOREAN` (lines 66–114):

- After the orientation sentence, insert the structural-invariant
  sentence (Hanja count = `<rt>` count, alternate one-to-one, never
  two consecutive `<rt>`).
- After the partial-conversion sentence, insert the per-word
  atomicity sentence.
- After the existing positive worked examples, append the two `NEVER`
  counter-examples.

### `tests/test_prompts.py`

Add `test_build_base_system_prompt_korean_variant_forbids_half_converted_word`
using the existing `variant_idx` / `pronunciation_idx` slicing pattern
from `test_build_base_system_prompt_korean_variant_calls_for_ruby`
(lines 256–275). Assertions:

- A phrase establishing per-word atomicity.
- The structural-invariant phrase.
- Both negative worked examples verbatim:
  - `'NEVER <ruby>地<rt>지</rt></ruby>갑'`
  - `'NEVER <ruby>帽<rt>모</rt><rt>자</rt></ruby>'`

All existing tests remain unchanged — the new rules are additive.

## Edge cases

- **Multi-syllable Sino-Korean word, only one syllable's Hanja
  confidently known.** Atomicity wins: leave the whole word in plain
  Hangul.
- **All syllables confident.** Wrap all in one outer `<ruby>` with
  alternating Hanja and `<rt>`, per the existing positive worked
  example (`<ruby>工<rt>공</rt>夫<rt>부</rt></ruby>`).
- **Cross-word partial conversion.** Still PREFERRED. The atomicity
  rule applies only within one word; lines can mix rubified and
  un-rubified Sino-Korean words.
- **Single-syllable Sino-Korean word.** Atomicity is trivially
  satisfied; structural invariant degenerates to the existing
  `<ruby>HANJA<rt>HANGUL</rt></ruby>` shape.

## Verification

- `make lint` clean.
- `uv run --frozen pytest tests/test_prompts.py` — new test passes,
  existing Korean variant tests still pass.
- Manual: replay `지갑이 되고 싶다면? 아님, 모자가 되고 싶다면?` through
  the app. The Variant row must either render `지갑` and `모자` as
  plain Hangul (when the model is not fully confident) or render them
  as full ruby (e.g. `<ruby>紙<rt>지</rt>匣<rt>갑</rt></ruby>` and
  `<ruby>帽<rt>모</rt>子<rt>자</rt></ruby>`). No
  `<ruby>地<rt>지</rt></ruby>갑` and no
  `<ruby>帽<rt>모</rt><rt>자</rt></ruby>`.
- Manual: re-run a known-working case (a line containing `工夫` or
  `學習`) and confirm the existing rubification still works — no
  regression to "always leave in Hangul".
