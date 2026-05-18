# Korean hanja variant: context overrides homophone ambiguity

## Context

Commit `929b21b` added a confidence gate to the Korean Variant row in
`build_base_system_prompt()` (`tutor/prompts.py`). The (b) "ambiguous
homophone" don't read:

> (b) it is an ambiguous homophone (e.g. 사기 = 詐欺 / 士氣 / 史記,
> 수도 = 首都 / 水道 / 修道) and the meaning is unclear

"and the meaning is unclear" already implies "if context
disambiguates, convert" — but only implicitly. The risk is that the
model interprets the don't lexically (`사기` is on the homophone list,
so leave it Hangul) and stays overly conservative when the
surrounding text unambiguously selects one sense, e.g.
`사기를 쳤다.` (clearly fraud / 詐欺) or `대한민국의 수도` (clearly the
country's capital / 首都). A missed hanja in an obviously-clear
context is a missed learning opportunity.

This change rewords (b) so the context-override is explicit and
anchored by positive examples reusing the same two homophones.

## Approach

A single sentence-level edit inside `build_base_system_prompt()` in
`tutor/prompts.py`. The (b) sub-bullet of the Korean Variant clause
becomes:

> (b) it is an ambiguous homophone (e.g. 사기 = 詐欺 / 士氣 / 史記,
> 수도 = 首都 / 水道 / 修道) AND the surrounding context does not
> pin down which sense is meant — when context CLEARLY selects one
> sense (e.g. 사기를 쳤다 → 詐欺를 쳤다, 대한민국의 수도 → 대한민국의
> 首都), go ahead and convert,

`AND` is uppercased to match the existing `ONLY` and `PREFERRED`
emphasis already used elsewhere in the Korean clause. The positive
examples reuse 사기 and 수도, so the model sees both directions of
each homophone (when to convert vs. when not).

Don'ts (a), (c), (d), the partial-conversion rule, the omit
threshold, and the Korean pronunciation bullet are unchanged.

## Critical files

- `tutor/prompts.py` — one sub-clause edit inside the Korean Variant
  instruction.
- `tests/test_prompts.py`:
  - Update `test_build_base_system_prompt_korean_variant_confidence_rule`
    to also assert the new `'context CLEARLY selects one sense'`
    phrase, the two positive examples
    (`'사기를 쳤다 → 詐欺를 쳤다'`, `'대한민국의 수도 → 대한민국의 首都'`),
    and the `'go ahead and convert'` phrasing. The existing homophone-
    list assertions stay green.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test on a Korean subtitle dataset:
   - `사기를 쳤다.` → expect `詐欺를 쳤다.` (context fixes meaning).
   - `사기가 높다.` → expect `士氣가 높다.` (context fixes meaning).
   - Bare `사기.` in isolation → `사기` stays in Hangul.
   - `대한민국의 수도` → expect `대한민국의 首都`.
   - Sanity: Chinese and Japanese Variant rows unchanged.
