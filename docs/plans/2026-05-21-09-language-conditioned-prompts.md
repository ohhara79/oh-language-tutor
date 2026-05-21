# Plan: language-conditioned system prompt

## Context

`build_base_system_prompt` in `tutor/prompts.py:24-215` unconditionally concatenates Chinese, Japanese, and Korean specific instructions (Variant row clauses + Pronunciation ruby bullets) into one monolithic prompt for every Explain request. When the learner is reading English or Spanish, the model still receives ~3-4 KB of CJK ruby rules that don't apply. This wastes context, distracts the model, and inflates token cost.

Goal: include only the language-specific sections that match `source_language`. When source isn't Chinese/Japanese/Korean, drop the Variant row entirely from the rubric. Match decision is on `source_language` only (target/native language doesn't affect ruby rules).

## Approach

1. **New `tutor/languages.py`** with substring-tolerant predicates so free-text inputs like "Mandarin Chinese" or "Japanese (Tokyo)" still route correctly:

   ```python
   def _matches(language: str, name: str) -> bool:
       return name in language.strip().casefold()

   def is_chinese(language: str) -> bool   # matches substring 'chinese'
   def is_japanese(language: str) -> bool  # matches substring 'japanese'
   def is_korean(language: str) -> bool    # matches substring 'korean'
   ```

   Move `is_japanese` out of `tutor/japanese.py` (which keeps only the kyūjitai conversion table/helpers). Update the single non-test caller at `tutor/web.py:31` and the import in `tests/test_japanese.py:5`. Per CLAUDE.md "no backwards-compat shims": delete the old `is_japanese` from `tutor/japanese.py` rather than re-exporting it.

2. **Extract per-language Variant clauses** from `tutor/prompts.py`:

   - `_variant_clause_chinese(source_language)` ← current lines 54-62
   - `_variant_clause_japanese(source_language)` ← current lines 62-75
   - `_variant_clause_korean(source_language)` ← current lines 75-126

   Add `_variant_row(source_language) -> str | None`: returns `None` (caller omits the whole `🔁 Variant:` line and its surrounding blank lines) when none of the three predicates match; otherwise returns the shared preamble (current lines 46-54, "raw line rewritten in the script variant…") plus exactly the matched language's clause. Predicates are mutually exclusive in practice.

3. **Extract per-language Pronunciation bullets** from the same file:

   - `_pronunciation_bullet_japanese()` ← lines 142-159
   - `_pronunciation_bullet_chinese()` ← lines 160-176
   - `_pronunciation_bullet_korean()` ← lines 177-194
   - `_dual_script_backstop_bullet()` ← lines 195-203 (keeps mentioning all three pairings — it's the universal `X / X` ban; gate only its *inclusion*, not its content)

   Assemble the Pronunciation block in order:
   - Header line + IPA preamble (lines 136-141) — **always**.
   - One matched-language bullet — when a CJK predicate matches.
   - Dual-script backstop — when any CJK predicate matches.
   - Phonetic-script catch-all (lines 204-206) — **always** (covers Spanish/Italian and the IPA-only English fallback).

   Replace the inline blocks in `build_base_system_prompt` with these helper calls. The Vocabulary template at line 128 stays generic and unchanged.

4. **Tests** in `tests/test_prompts.py`: existing tests that pass `'Mandarin Chinese'` / `'Japanese'` / `'Korean'` stay green under substring matching. Two break and need surgery:
   - `test_build_base_system_prompt_includes_ipa_for_every_language` (line 170) — split into per-language IPA tests (`_chinese_ipa`, `_japanese_ipa`, `_korean_ipa`, `_phonetic_script_ipa` using `'Spanish'`).
   - The dual-script backstop test at line 286 stays green because the bullet still names all three pairings when included.

   Add absence tests:
   - `('English', 'Korean', 'intermediate')` → no `🔁 Variant:`, no `kyūjitai` / `furigana` / `pinyin` / `hanja` / `고유어` / `漢字`, no `NEVER emit two halves`, but `[ˈola]` still present.
   - `('Chinese', …)` → omits Japanese + Korean clause anchor strings; symmetric for Japanese and Korean.
   - `test_build_base_system_prompt_substring_match_mandarin_chinese` — explicit `'Mandarin Chinese'` produces Chinese clauses.

   New `tests/test_languages.py` (or extend `test_japanese.py`): exercise substring matching and mutual exclusion (`is_chinese('Japanese')` is False, `is_japanese('Mandarin Chinese')` is False, etc.). Update `test_japanese.py` to import `is_japanese` from `tutor.languages`.

## Files to touch

- `tutor/prompts.py` — extract helpers, condition the Variant row and Pronunciation block on `source_language`.
- `tutor/languages.py` — **new**, holds the three predicates.
- `tutor/japanese.py` — remove `is_japanese`; keep the kyūjitai helpers.
- `tutor/web.py` — update import on line 31.
- `tests/test_prompts.py` — split the multi-language IPA test, add absence tests, add substring-match test.
- `tests/test_japanese.py` — update `is_japanese` import, keep its existing assertions on `is_japanese`.
- `tests/test_languages.py` — **new**, covers `is_chinese`/`is_korean` plus mutual exclusion.

## Verification

1. `make lint` — catches dangling imports and basedpyright type errors.
2. `uv run --frozen pytest tests/test_prompts.py tests/test_languages.py tests/test_japanese.py` — focused suite for the touched modules.
3. `uv run --frozen pytest` — full suite, ensures `web.py` + thread-pool integration paths still work.
4. Manual smoke: run the web app (per `r.sh`), open the same dataset four times with Learning language set to Korean, Japanese, Chinese, English. Click Explain on one line per session and confirm:
   - Korean → Variant row with hanja/Hangul ruby; no `pinyin` / `furigana` text.
   - Japanese → Variant row with furigana; GROUND TRUTH block when kanji present.
   - Chinese → Variant row with pinyin ruby; no Japanese/Korean clauses.
   - English → no Variant row in the rubric; explanation has IPA but no ruby / no dual-script backstop wording.

## Step-by-step implementation order

1. Add `tutor/languages.py` with the three predicates.
2. Move `is_japanese` import in `tutor/web.py` and `tests/test_japanese.py`; delete from `tutor/japanese.py`.
3. Extract Variant clause helpers + `_variant_row` in `tutor/prompts.py`; replace lines 46-126 in `build_base_system_prompt`.
4. Extract Pronunciation bullet helpers; replace lines 142-203.
5. Add absence tests; split the multi-language IPA test; add `tests/test_languages.py`.
6. Run `make lint` and the full pytest suite.
7. Manual smoke through the web app for all four source-language cases.
