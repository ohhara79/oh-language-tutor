# Korean Variant: add ruby (Hangul ↔ Hanja)

## Context

The 🔁 Variant row already carries per-line ruby pronunciation for Chinese
(per-character pinyin) and Japanese (whole-word furigana). For Korean, the
Variant row rewrites the line in the *opposite* script (Hangul → hanja or
hanja → Hangul, `tutor/prompts.py:75-105`) but uses no ruby — the learner
sees only the rewrite in plain text and has to mentally pair it back to the
input form.

Bring Korean to parity by wrapping the Variant rewrite's Sino-Korean spans in
HTML `<ruby>` so the *other script* sits above each character:

- **Hanja in the variant → ruby in Hangul** (the Hangul reading sits above
  each hanja). Fires when the input was pure Hangul and the variant added
  hanja.
- **Hangul (of a Sino-Korean word) in the variant → ruby in hanja** (the
  hanja form sits above each Hangul syllable). Fires when the input
  contained hanja and the variant rewrote those words in Hangul.

Per-character granularity (Sino-Korean is 1 hanja = 1 Hangul syllable, so the
mapping is unambiguous — same shape as the existing Chinese pinyin rule).
Particles (조사), verb/adjective endings, and native Korean words (고유어)
are never wrapped in either direction.

Scope is the Variant row only. The Korean Vocabulary row keeps its current
`학습 / 學習 (haksŭp, [haks͈ɯp])` dual-script + romanization format
unchanged, and Expression/Context Korean prose stays plain.

Prompt-only change. The rendering pipeline already passes raw HTML through
unchanged (`tutor/markdown_util.py` + `| safe` in the line/index templates),
as confirmed in production for Japanese and Chinese.

## Approach

Single-file edit to the Korean clause of the Variant row in
`build_base_system_prompt` (`tutor/prompts.py:75-105`). Extend both
direction branches with a per-character `<ruby>` wrapping instruction, and
add carve-outs so unconverted spans (kept in input form because the
conversion was uncertain) stay bare — better no ruby than wrong ruby.

### Branch 1 — input contains hanja (variant rewrites to Hangul)

After the existing per-hanja-reading-selection rules: wrap each
*successfully-converted* Sino-Korean Hangul span in per-character `<ruby>`
with the original hanja (from the input line) as the `<rt>` above each
syllable. Hanja left in place because the reading was uncertain stay bare.

### Branch 2 — input is pure Hangul (variant rewrites to hanja)

After the existing confidence-gated hanja-conversion rules: wrap each
*successfully-converted* hanja span in per-character `<ruby>` with the
original Hangul syllable(s) (from the input line) as the `<rt>` above each
hanja. Hangul words the variant kept as-is because the hanja was uncertain
stay bare.

### Worked examples embedded in the prompt

- Input `대한민국의 수도는 서울이다.` → variant
  `<ruby>大<rt>대</rt>韓<rt>한</rt>民<rt>민</rt>國<rt>국</rt></ruby>의 <ruby>首<rt>수</rt>都<rt>도</rt></ruby>는 서울이다.`
- Input `工夫합니다.` → variant
  `<ruby>공<rt>工</rt>부<rt>夫</rt></ruby>합니다.`
- Input `音樂을 들었다.` → variant
  `<ruby>음<rt>音</rt>악<rt>樂</rt></ruby>을 들었다.`

### Symmetry / safety clauses (unchanged)

- "Wrong character teaches the wrong thing" framing already in the clause
  also justifies the "no ruby on uncertain spans" carve-out.
- The dual-script duplicate-half guard at `tutor/prompts.py:174-182` targets
  the Vocabulary row only (single rewrite vs. `A / B` pair) — no edit.
- The "skip any empty section does not apply to this row" override at
  `tutor/prompts.py:46-54` already covers Korean — no edit.

## Files

- `tutor/prompts.py` — extend the Korean Variant clause inside
  `build_base_system_prompt` (single string-literal edit).
- `tests/test_prompts.py` — two new tests parallel to the existing
  `test_build_base_system_prompt_chinese_variant_calls_for_ruby` and
  `test_build_base_system_prompt_japanese_variant_calls_for_ruby`:
  - `test_build_base_system_prompt_korean_variant_calls_for_ruby` — assert
    the Korean half of the Variant clause mentions `<ruby>`, `<rt>`, and
    both directions.
  - `test_build_base_system_prompt_korean_variant_ruby_worked_examples` —
    assert one ruby example from each direction appears verbatim.

No backend, template, CSS, JS, or data-table changes. No new dependencies.
No changes to Korean Vocabulary, Expression, or Context rows.

## Verification

1. `make lint` — basedpyright + ruff clean.
2. `uv run --frozen pytest tests/test_prompts.py` — all assertions pass.
3. Manual smoke in the web UI:
   - **Pure Hangul input** (`대한민국의 수도는 서울이다.`): Variant row
     renders with hanja in the line and Hangul as ruby above each hanja;
     particles 의 / 는 and copula 이다 stay bare; DevTools shows real
     `<ruby><rt>` elements.
   - **Mixed-script input** (`工夫합니다.`): Variant row renders with
     Hangul in the line and hanja as ruby; verb ending 합니다 stays bare.
   - **Pure hanja input** (`學習`): Variant row renders
     `<ruby>학<rt>學</rt>습<rt>習</rt></ruby>`.
   - **Pure native-Korean input** (`아름답다.`): Variant row stays omitted
     (existing behavior — nothing to convert).
   - **Uncertain Sino-Korean** (a line containing 사기 with ambiguous
     context): the variant keeps that word in its input form with no ruby.
   - **Cross-language regression**: Japanese and Chinese Variant rows still
     render their existing furigana / pinyin ruby unchanged.
