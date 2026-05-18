# Korean Variant: hanja → Hangul when input contains hanja

## Context

Today the Variant row in Korean explanations only goes one direction: it takes a Hangul input line and substitutes Sino-Korean words with their hanja form (`tutor/prompts.py:54-74`). When a user feeds in a line that already contains hanja, the Variant row has nothing useful to add — it can't go "more hanja," and the current prompt has no instruction to go the other way.

The user wants the inverse direction supported: if the input line contains any hanja, the Variant row should rewrite the line in pure Hangul (the reading the learner would actually pronounce). The Vocabulary row should also flip its dual-script order (`漢字 / Hangul` instead of `Hangul / 漢字`) for vocab items whose source word appears as hanja in the input, so the learner sees the form they're reading first.

This is a prompt-only change. The Variant and Vocabulary rows are LLM-generated text, not stored data — there is no schema or codegen involved.

## Approach

Single-file edit to `tutor/prompts.py`. Two sections change:

### 1. Variant row — `tutor/prompts.py:54-74`

Restructure the Korean Variant instruction as a top-level branch on input script:

- **If the input line contains any hanja character:** rewrite the entire line in Hangul. For each hanja, use the surrounding context to pick the correct reading. Multi-reading hanja (e.g. 樂 → 락/낙/요/악, 行 → 행/항, 不 → 불/부, 北 → 북/배) must be disambiguated by meaning in context. If a hanja's reading is genuinely uncertain in context, leave it in place rather than guess — a wrong Hangul reading teaches the wrong pronunciation, just as a wrong hanja teaches the wrong form. Partial conversion (mixed script with the uncertain hanja remaining) is preferred over a wrong reading.
- **Otherwise (input is pure Hangul):** existing rule applies unchanged — substitute Sino-Korean words with their hanja form, with the four existing confidence gates (proper nouns without pinned context, ambiguous homophones, Sino-vs-native uncertain, rare/literary hanja). Particles (조사) and verb/adjective endings always stay in Hangul.

Preserved framing:
- "Omit the entire row only when no word can be converted with confidence" — applies symmetrically to both directions.
- "Wrong form teaches the learner the wrong thing" — generalize from "wrong hanja" to "wrong character in either direction."
- Mixed-script intermediate is preferred over a wrong conversion.

### 2. Vocabulary row — `tutor/prompts.py:103-115`

Add a rule: when the vocab item's source word appears in the input line in hanja form, flip the dual-script ordering to **`漢字 / Hangul`** (hanja first, Hangul second). When the source word appears in Hangul, keep the current **`Hangul / 漢字`** ordering. The confidence gates and the "drop the slash when uncertain or native" rule are unchanged.

Worked examples to embed in the prompt:
- Input contains `工夫합니다`, vocab item is 공부: emit `工夫 / 공부 (kongbu, [koŋbu]) → study`.
- Input contains `공부합니다`, vocab item is 공부: emit `공부 / 工夫 (kongbu, [koŋbu]) → study` (existing behavior).
- Input contains `아름답다` (native Korean): emit `아름답다 [a̠ɾɯmda̠p̚t͈a̠] → beautiful` (no slash, existing behavior).

### 3. Dual-script duplicate guard — `tutor/prompts.py:116-119`

The existing rule "NEVER emit two halves that are character-for-character identical" is order-agnostic and already covers the flipped layout. No change.

## Files

- `tutor/prompts.py` — Variant row (lines 54–74) and Korean Vocabulary row (lines 103–115). Single-file change.

No tests, data models, or code paths to touch.

## Verification

1. `make lint` passes.
2. Manual end-to-end check with three Korean inputs through `uv run --frozen` (the project's standard run command):
   - **Pure Hangul:** `대한민국의 수도는 서울이다.` → Variant row should show `大韓民國의 首都는 서울이다.` (current behavior preserved; nothing regresses).
   - **Mixed script:** `工夫합니다` → Variant row should show `공부합니다`.
   - **Pure hanja:** `學習` → Variant row should show `학습`.
3. Vocabulary-row ordering flips correctly: feeding a line containing `工夫` should produce a vocab entry `工夫 / 공부 (...)`, while feeding `공부` produces `공부 / 工夫 (...)`.
4. Multi-reading hanja sanity check: `音樂` → `음악` (not `음락`); `行動` → `행동` (not `항동`); confirm context-driven disambiguation works for at least one tricky case (e.g. `樂園` → `낙원`).
