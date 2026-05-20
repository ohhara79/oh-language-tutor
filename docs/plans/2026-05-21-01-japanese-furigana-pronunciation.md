# Show Japanese pronunciation as furigana

## Context

Today, Japanese explanations show kanji pronunciation as parenthetical hiragana plus IPA, e.g. `学校 / 學校 (がっこう, [ɡakkoː])`. The learner has to map each kana back to a specific kanji mentally, and the parenthetical only appears on the Vocabulary row — kanji in the 🔁 Variant rewrite or in phrases quoted inside the Expression/Context rows carry no reading at all. Furigana (ruby annotations above the kanji) is the conventional way to show readings in Japanese pedagogy, and it works uniformly everywhere kanji appears.

The end-to-end rendering pipeline already supports HTML `<ruby>` tags:

- The model output is parsed by `python-markdown` with the `extra` extension (`tutor/markdown_util.py:38-41`), which passes raw HTML through unchanged.
- Jinja2 renders the explanation with the `| safe` filter (`tutor/templates/partials/line.html:6`, `tutor/templates/index.html:65`), so HTML reaches the browser intact.
- Browsers natively render `<ruby><rt>` with sensible defaults — no CSS or JS work is required.

The change is therefore a **prompt-only** edit: tell the model to wrap every kanji-bearing Japanese span in `<ruby>` with the reading, and drop the now-redundant parenthetical hiragana on the Vocabulary row. Prompt tests update to match.

## Approach

### Format

Whole-word ruby — one `<rt>` per `<ruby>` span, covering the whole word. Mora-to-kanji splits like 学校 → がっ+こう are ambiguous, so per-kanji ruby would tempt the model into wrong splits.

Vocabulary row, with kyūjitai variant:
```
<ruby>学校<rt>がっこう</rt></ruby> / <ruby>學校<rt>がっこう</rt></ruby> [ɡakkoː] → 학교
```

Vocabulary row, no kyūjitai variant (okurigana sits inside the `<ruby>` span):
```
<ruby>受け入れる<rt>うけいれる</rt></ruby> [ɯke̞iɾe̞ɾɯ] → 받아들이다
```

The parenthetical `(がっこう, …)` is dropped — the ruby already carries the kana. IPA stays in brackets after the word, consistent with every other language's pronunciation rule.

Pure-kana words (e.g. `ありがとう`) and pure-ASCII tokens are not wrapped — `<ruby>` is applied only when the span contains at least one kanji.

### Scope

Furigana applies to every kanji-bearing Japanese span anywhere in the explanation:

- 🔁 Variant row — the kyūjitai rewrite gets furigana over each kanji-bearing word.
- 📚 Vocabulary row — both shinjitai and kyūjitai forms get furigana; parenthetical hiragana is removed (IPA stays).
- 💡 Expression / 🎬 Context rows — any quoted Japanese phrase or word inside the target-language prose gets furigana.

The dual-script duplicate-half guard (`prompts.py:131-137`) still applies: the kanji inside the two `<ruby>` spans on either side of `/` must not be character-for-character identical; drop the slash and the duplicate `<ruby>` span if so.

## Files to modify

- `tutor/prompts.py`
  - Lines 100-107 (Japanese bullet in "Pronunciation notation"): rewrite to specify the `<ruby><rt>` format and extend it to every kanji-bearing span anywhere in the explanation. Update the worked examples (`学校 / 學校 …` and `受け入れる …`) to the ruby form. Drop the "Hiragana and IPA go in the same parens" sentence.
  - 🔁 Variant row Japanese clause (around lines 49-54): add an instruction that the emitted kyūjitai rewrite is wrapped in whole-word `<ruby>` spans.
  - Lines 131-137 duplicate-half rule: restate so it covers the kanji-inside-`<ruby>` comparison for Japanese.

- `tests/test_prompts.py`
  - `test_build_base_system_prompt_mentions_japanese_kyujitai` (line 47): replace the `'学校 / 學校'` assertion with assertions that the prompt contains the new ruby-form example.
  - `test_build_base_system_prompt_includes_ipa_for_every_language` (line 87): replace the `'(うけいれる, [ɯke̞iɾe̞ɾɯ])'` assertion with the new bracketed-IPA-only form.
  - Add a new test that the Japanese clauses mention `<ruby>` and `<rt>` so the rule is not silently lost.

No backend, template, CSS, or JS changes. No new dependencies.

## Verification

1. `make lint` — basedpyright + ruff pass.
2. `uv run --frozen pytest tests/test_prompts.py` — updated assertions pass.
3. Manual smoke test in the web UI:
   - Load a Japanese subtitle, click Explain on a kanji-bearing line.
   - Vocabulary row shows kanji with kana above (ruby) and IPA in brackets; no parenthetical hiragana.
   - Variant row's kyūjitai rewrite renders with furigana.
   - Quoted Japanese phrases inside Expression/Context render with furigana.
   - DevTools shows real `<ruby><rt>…</rt></ruby>` elements.
