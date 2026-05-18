# Kyūjitai: feed Vocabulary too, and complete the lookup table

## Context

Commit `314c4ca` made the 🔁 Variant row reliable by precomputing the
kyūjitai rewrite of the target line and injecting it as a GROUND TRUTH
block. Two follow-up gaps emerged:

1. **Vocabulary lines still drop the kyūjitai form.** The pronunciation
   rule asks for `学校 / 學校 (がっこう, [ɡakkoː]) → 학교` when the word
   has a kyūjitai form, but vocab items are picked by the LLM at
   generation time and the model's kyūjitai recall is uneven. The
   Variant row was fine because its content is fully pre-computed; the
   per-vocab decision is not.

2. **The lookup table itself had gaps.** A diff against a curated
   reference set of well-attested Tōyō/Jōyō simplifications turned up
   41 missing entries across two audit passes — including very common
   ones like 来→來, 内→內, 広→廣, 変→變, 真→眞, 単→單, 将→將, 参→參,
   温→溫, 済→濟, 砕→碎, 継→繼, 縁→緣, plus animal/plant names common
   in subtitles (鴎→鷗, 鴬→鶯, 鯵→鰺, 蝉→蟬). When a line uses these
   kanji the converter would leave them as shinjitai, so the row
   reverted to LLM-recall — which was what we were trying to avoid.

This change closes both gaps.

## Approach

### Part 1 — feed vocab through GROUND TRUTH

Add `relevant_kyujitai_mappings(text: str) -> dict[str, list[str]]` to
`tutor/japanese.py`. It returns the subset of the lookup table whose
keys appear in *text*, deduplicated, in first-appearance order.

Extend `build_system_prompt` in `tutor/prompts.py` with a keyword-only
`kyujitai_mappings: dict[str, list[str]] | None = None` parameter
(sibling to the existing `kyujitai_variant`). When the mapping is
non-empty, append a second bullet under the existing GROUND TRUTH
header:

```
- Per-kanji kyūjitai mappings for the target line — use these when
  emitting Vocabulary items containing any of these kanji, applying
  the same "[A|B|C] = pick by meaning" rule as the Variant row:
      学 → 學
      経 → 經
      弁 → 辨 / 瓣 / 辯 / 辮  (pick by meaning)
```

Single-candidate entries render as `K → K′`; multi-candidate entries
add a "(pick by meaning)" hint, reusing the bracket-resolution rule
already established for the Variant row.

Update the Japanese pronunciation bullet in `build_base_system_prompt`
(`tutor/prompts.py:72-78`) so it points at the GROUND TRUTH mappings
as the source of truth — "those mappings are the source of truth, not
your recall."

Wire it in `tutor/web.py`'s `explain` handler: compute
`relevant_kyujitai_mappings(target.raw)` alongside the existing
`to_kyujitai_template(target.raw)` and forward both kwargs to
`build_system_prompt`.

### Part 2 — expand the lookup table 280 → 321

Edit `tutor/data/shinjitai_kyujitai.json` to add 41 missing entries
identified across two audit passes:

- First pass (23 audit-confirmed misses + a handful of neighbours, 27
  entries): 来, 内, 広, 変, 舎, 真, 単, 将, 徴, 殻, 厨, 即, 既, 堕, 青,
  隷, 窓, 寛, 済, 温, 砕, 継, 縁, 蝉, 麺, 虫, 黄.
- Second pass (14 entries surfaced by a wider candidate sweep): 参,
  鴎, 鴬, 鯵, 嘱, 醗, 賎, 晋, 壷, 屏, 掴, 掻, 剥, 遥.

Tighten the JSON `_notes` field to be honest about scope and reference
the regression-guard test.

Add a pinned regression list `_PINNED_ENTRIES` in
`tests/test_japanese.py` (~45 well-attested pairs including all 41
newly added) and a `test_table_contains_pinned_common_entries` that
fails CI if a future edit silently drops any of them — closing the
class of bug that produced this round of fixes.

## Why both bullets live under one GROUND TRUTH header

The Variant rewrite and the per-kanji mappings are the same source of
truth (the lookup table) at two granularities. Co-locating them under
one GROUND TRUTH header lets the LLM see the bracket-resolution rule
once and apply it to both the Variant row and any Vocabulary items
containing multi-candidate shinjitai like 弁.

## Critical files

- `tutor/data/shinjitai_kyujitai.json` — +41 entries; tighter `_notes`.
- `tutor/japanese.py` — `relevant_kyujitai_mappings(text)`.
- `tutor/prompts.py` — `build_system_prompt` gains
  `kyujitai_mappings` kwarg; GROUND TRUTH renders both bullets;
  Japanese pronunciation rule references the mappings.
- `tutor/web.py` — compute and forward both kyūjitai kwargs.
- `tests/test_japanese.py` — `_PINNED_ENTRIES` regression guard, new
  converter spot-checks for the 41 additions, full coverage of
  `relevant_kyujitai_mappings`.
- `tests/test_prompts.py` — system-prompt assertions for the new
  bullet (rendered single- and multi-candidate entries, presence /
  absence on empty mapping, Japanese pronunciation rule references
  GROUND TRUTH).
- `tests/test_web.py` — integration test now asserts the per-kanji
  bullet appears alongside the variant template for Japanese sources.

## Verification

1. `uv run --frozen pytest -q` — 220 → 231 passing.
2. `make lint` — clean (ruff + basedpyright).
3. Manual smoke test:
   - Launch the app, ingest a Japanese subtitle; set
     `Learning = Japanese`, `Native = Korean`,
     `Level = intermediate`.
   - Click Explain on lines containing kanji that previously dropped
     from the Variant row (来, 内, 広, 変, 真, 単, 将, 参, 鴎, 嘱,
     醗, 晋, 遥, 賎). Confirm the 🔁 row rewrites each one.
   - Click Explain on a line where vocab previously dropped the
     dual-script form (e.g. lines with long-tail kanji 渋, 缶, 芸,
     観, 関, 経). Confirm vocab items render in
     `shinjitai / kyūjitai (kana, IPA) → translation`.
   - Click Explain on an ambiguous-shinjitai line: **弁護士** vs
     **花弁**. Confirm the Variant row and the matching vocab item
     pick the same kyūjitai (辯 vs 瓣) by context.
   - Sanity: Chinese / Korean / English sources still behave as
     before.

## Out of scope (revisit later if needed)

- Post-processing the streamed explanation to enforce that vocab uses
  the listed kyūjitai. The system-prompt reference is sufficient in
  practice; mid-stream parsing adds complexity for little gain.
- Multi-candidate refinement for 余/缶/芸 (the bare-classical sense).
  Documented in JSON `_notes` as a known limitation.
- Rare/specialist kanji (e.g. 梼→檮 — surfaces almost only in the
  Kōchi place name 梼原). Add them on demand as learners report gaps;
  the pinned regression test will protect new entries.
