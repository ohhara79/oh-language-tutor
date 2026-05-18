# Hybrid kyūjitai: deterministic substitution + LLM context disambiguation

## Context

Commit `a756526` added a 🔁 Variant row that asks the LLM to rewrite a
Japanese line in kyūjitai (旧字体). In practice the model misses many
kanji because kyūjitai is rarely seen in modern Japanese — it converts
the common pairs (学→學, 国→國, 体→體) but drops the long tail (渋→澁,
缶→罐, 芸→藝, 観→觀, …).

Some shinjitai map to **multiple** kyūjitai whose choice depends on
meaning:

| Shinjitai | Kyūjitai options                  | Disambiguation hinges on            |
|-----------|-----------------------------------|--------------------------------------|
| 弁        | 辨 / 瓣 / 辯 / 辮                 | 弁護士 → 辯, 弁当 → 辨, 花弁 → 瓣, 弁髪 → 辮 |
| 画        | 畫 / 劃                           | 絵画 → 畫, 区画 → 劃 |

A pure character-level lookup table cannot resolve these — but the
LLM, given the surrounding line and context, can. The design is: do
the unambiguous substitutions deterministically, leave the ambiguous
ones as bracketed alternatives, and ask the LLM to pick one form at
each bracket using the line's meaning.

## Approach

1. **Bundle the lookup table** at `tutor/data/shinjitai_kyujitai.json`.
   Values are **lists**, so a single key can carry multiple
   alternatives:

   ```json
   {
     "_notes": "...",
     "学": ["學"],
     "国": ["國"],
     "弁": ["辨", "瓣", "辯", "辮"],
     "画": ["畫", "劃"]
   }
   ```

   Curated from the 1949 Tōyō and post-1981 Jōyō simplifications.
   Characters whose shinjitai equals their kyūjitai are deliberately
   absent — the converter leaves unmapped characters verbatim.
   Hatchling (uv's default build backend, inferred from the absent
   `[build-system]` section in `pyproject.toml`) auto-includes files
   inside the package, so no `package-data` declaration is needed.

2. **Add `tutor/japanese.py`** with:
   - `_TABLE: dict[str, list[str]]` loaded once at import time from
     the JSON, with the `_notes` key filtered out.
   - `to_kyujitai_template(text: str) -> str | None`: per-character
     lookup. For each character: not in the table → emit verbatim;
     one candidate → substitute directly; multiple → emit
     `[A|B|C]`. Returns `None` when no character was rewritten or
     bracketed, so callers can omit the Variant row.
   - `is_japanese(language: str) -> bool`: case- and whitespace-
     insensitive match against `"japanese"`, since `_validate_audience`
     in `tutor/web.py` accepts any non-empty string.

3. **Extend `build_system_prompt`** in `tutor/prompts.py` with a
   keyword-only `kyujitai_variant: str | None = None` parameter. When
   supplied, append a GROUND TRUTH block after the existing
   extras-text section. The block states the verbatim rule for the
   common case and teaches the `[A|B|C]` resolution rule for
   ambiguous positions. The `PromptTooLargeError` size check still
   applies after the block is appended.

4. **Update the Variant row instruction** in
   `tutor/prompts.py:46-53` so the Japanese clause points at the
   GROUND TRUTH block: copy verbatim, resolve `[A|B|C]` groups by
   context. The Chinese clause is unchanged.

5. **Wire it in `tutor/web.py`'s `explain` handler**: compute
   `to_kyujitai_template(target.raw) if is_japanese(source_language)
   else None` before `build_system_prompt`, and forward the result via
   the new kwarg. `build_explain_user_message` is unchanged.

## Why the system prompt (and not the user message)

The system-prompt path frames the precomputed value as a constraint
the LLM operates under, not data mixed into the line it's reasoning
about. The model treats system content as instructions, which matches
the intent ("use this verbatim; resolve brackets by context"). The
system prompt is already built per request here
(`build_system_prompt` takes the audience args fresh each call), so
adding a request-specific block is consistent with the existing
pattern.

## Critical files

- `tutor/data/shinjitai_kyujitai.json` — new data file (~280 entries).
- `tutor/japanese.py` — new module: `to_kyujitai_template`,
  `is_japanese`.
- `tutor/prompts.py` — Variant row Japanese clause + new
  `kyujitai_variant` kwarg on `build_system_prompt`.
- `tutor/web.py` — call `to_kyujitai_template` before
  `build_system_prompt`; forward the result.
- `tests/test_japanese.py` — new. Cover unambiguous substitution,
  bracketed multi-mapping (`弁護士` → `[辨|瓣|辯|辮]護士`), kana
  pass-through, `None` for no-conversion cases, table invariants,
  `is_japanese` case/whitespace insensitivity.
- `tests/test_prompts.py` —
  - GROUND TRUTH block appears verbatim when `kyujitai_variant` is
    supplied.
  - Default call omits the block.
  - The Variant row Japanese clause references GROUND TRUTH and the
    `[A|B|C]` resolution rule.
- `tests/test_web.py` — two integration tests: Japanese source
  injects the GROUND TRUTH block into the system prompt sent to the
  fake SDK client; non-Japanese source does not.

## Verification

1. `uv run --frozen pytest -q` — existing tests still pass plus the
   new ones (203 → 220).
2. `make lint` — clean (ruff + basedpyright).
3. Manual smoke test:
   - Launch the app, ingest a Japanese subtitle (e.g. the
     `フレンズ.S01E01.srt` already in the working tree); set
     `Learning = Japanese`, `Native = Korean`, `Level = intermediate`.
   - Click Explain on a line with long-tail kanji (渋, 缶, 芸, 観,
     関, 経, 戦, 党, …). Confirm the 🔁 Variant row shows the
     kyūjitai form for every one, matching the output of
     `uv run --frozen python -c "from tutor.japanese import to_kyujitai_template; print(to_kyujitai_template('…'))"`
     (modulo bracket resolution).
   - Click Explain on a line containing an ambiguous shinjitai in a
     clear context: **弁護士** → expect 辯護士; **花弁** → expect 花瓣.
   - Click Explain on a hiragana/katakana-only line, and on a
     kanji-only line whose chars have no kyūjitai (人山川). Confirm
     no Variant row appears.
   - Sanity: Chinese and Korean/English sources still behave as
     before.

## Out of scope (revisit later if needed)

- Deterministic kyūjitai for vocabulary items. Vocab still goes
  through the LLM; the prompt already asks for dual-script when
  applicable.
- Validating that the LLM resolved every `[A|B|C]` group (e.g. a
  post-hoc regex on the stored explanation). Worth adding if we see
  brackets leaking into rendered output, but not in scope for v1.
- Distinguishing kyūjitai from Taiwan-traditional Chinese where they
  differ. The Variant row is labelled "kyūjitai" so the learner knows
  which convention they are seeing.
