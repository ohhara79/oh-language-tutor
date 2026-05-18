# Kyūjitai: third-pass audit — fill remaining jōyō-kanji gaps

## Context

The shinjitai → kyūjitai table in `tutor/data/shinjitai_kyujitai.json`
powers the 🔁 Variant row and the per-vocab kyūjitai bullet for Japanese
sources (see `to_kyujitai_template` / `relevant_kyujitai_mappings` in
`tutor/japanese.py`, wired through `build_system_prompt`). Two earlier
audits brought the table from 280 → 321 entries (commits `314c4ca`,
`d525011`; see `2026-05-18-11-…` and `2026-05-18-12-…`).

A third systematic sweep cross-referenced the table against the 2010
Jōyō Kanji appendix (常用漢字表 付表「印刷標準字体と異なる康熙字典体」)
and the original 1946 Tōyō / 1981 Jōyō simplifications, restricted to
the pairs where the modern jōyō glyph and its Kangxi/kyūjitai form
occupy **different Unicode code points** — the only pairs the
per-character converter can address. Eight gaps surfaced. All other
appendix entries (葛, 蓋, 鬱, 餌, 籠, 詮, 遡, 遜, 謎, 箋, 槽, 蔽, 諧,
嗅, 璧, 楷, 鷹, 訃, 拳, 哺, 嫉, 唾, 慄, 賂, 嘲, …) differ only in glyph
shape within one code point and remain out of scope by design.

## Approach

### 1. Expand the JSON table 321 → 329

Add 8 single-candidate entries to `tutor/data/shinjitai_kyujitai.json`,
inserted in the file's existing roughly-Unicode-ordered layout:

| shinjitai | kyūjitai | origin |
|-----------|----------|--------|
| 没 U+6CA1 | 沒 U+6C92 | original Tōyō/Jōyō |
| 頬 U+982C | 頰 U+9830 | 2010 jōyō addition |
| 餅 U+9905 | 餠 U+9920 | 2010 jōyō addition |
| 痩 U+75E9 | 瘦 U+7626 | 2010 jōyō addition |
| 嘘 U+5618 | 噓 U+5653 | 2010 jōyō addition |
| 喩 U+55A9 | 喻 U+55BB | 2010 jōyō addition |
| 填 U+586B | 塡 U+5861 | 2010 jōyō addition |
| 挿 U+633F | 插 U+63D2 | original 1981 jōyō |

None of the eight has multiple Kangxi candidates by meaning, so all
are single-element lists (no `[A|B|C]` brackets).

### 2. Pin the new entries against regression

Append a "Third-pass audit additions:" block to `_PINNED_ENTRIES` in
`tests/test_japanese.py`, mirroring the existing first- and second-pass
blocks. `test_table_contains_pinned_common_entries` then fails CI if a
future edit silently drops any of them.

### 3. Add converter spot-checks

Extend `test_to_kyujitai_newly_added_entries` with realistic-context
spot-checks for each new pair (`没頭`, `頬骨`, `煎餅`, `痩身`,
`嘘つき`, `比喩`, `補填`, `挿入`).

## Critical files

- `tutor/data/shinjitai_kyujitai.json` — +8 entries.
- `tests/test_japanese.py` — `_PINNED_ENTRIES` gains 8 pairs;
  `test_to_kyujitai_newly_added_entries` gains 8 assertions.

Functions reused unchanged:

- `to_kyujitai_template` (`tutor/japanese.py`) — picks up the new
  entries the moment the JSON is updated.
- `relevant_kyujitai_mappings` (`tutor/japanese.py`) — same.
- `build_system_prompt` (`tutor/prompts.py`) — already renders both
  the Variant template and the per-kanji mappings, so the additions
  flow into the prompt with no code change.

## Verification

1. `uv run --frozen pytest -q` — all green, including the new
   spot-checks and the pinned-entries regression guard.
2. `make lint` — clean (ruff + basedpyright + xenon).
3. JSON-load sanity:
   `uv run --frozen python -c "from tutor.japanese import _TABLE;
   [print(c, _TABLE[c]) for c in '没頬餅痩嘘喩填挿']"` — prints the 8
   new pairs.
4. Manual smoke test: ingest a Japanese subtitle, click Explain on
   lines containing each of 没, 頬, 餅, 痩, 嘘, 喩, 填, 挿; confirm
   the 🔁 Variant row rewrites every one and matching vocab items
   render in `shinjitai / kyūjitai (kana, IPA) → translation`. Sanity:
   Chinese / Korean / English sources still behave unchanged.
