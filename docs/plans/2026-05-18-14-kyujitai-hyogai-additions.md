# Kyūjitai: fourth-pass audit — extend to hyōgai (表外漢字)

## Context

The shinjitai → kyūjitai table now has 329 entries after three jōyō
audit passes (commit `4563565`; see plans `2026-05-18-11/12/13-…`).
The user reports more kyūjitai are missing among the hyōgai (表外漢字 —
non-jōyō) kanji. Earlier passes already smuggled in commonly-seen
hyōgai pairs (鴎→鷗, 鴬→鶯, 鯵→鰺, 屏→屛, 掴→摑, 壷→壺, 賎→賤, …)
without making the scope expansion explicit. This pass makes the
hyōgai coverage explicit and fills the obvious gaps.

The natural reference for hyōgai shinjitai/kyūjitai pairs is the
**2000 表外漢字字体表** appendix, which lists 22 簡易慣用字体 (informal
simplified forms) alongside their 印刷標準字体 (Kangxi-derived standard
form). Of those 22, five are already in the table (鴬→鶯, 掴→摑, 鴎→鷗,
屏→屛, 麺→麵). The remaining 17 are missing, plus two non-list pairs
commonly seen in subtitles (凛→凜 and 篭→籠).

## Approach

### 1. Expand the JSON table 329 → 348

Insert 19 single-candidate entries into
`tutor/data/shinjitai_kyujitai.json`, placed near their Unicode
code-point neighbours.

From the 表外漢字字体表 簡易慣用字体 list (17):
唖→啞, 焔→焰, 噛→嚙, 侠→俠, 躯→軀, 鹸→鹼, 麹→麴, 桧→檜, 醤→醬,
蝋→蠟, 砿→礦, 蕊→蘂, 騨→驒, 弯→彎, 繍→繡, 撹→攪, 諌→諫.

Extras (2): 凛→凜 (jinmeiyō; 凜 is the traditional/standard form),
篭→籠 (篭 is a widely-encountered simplified variant of jōyō 籠).

All 19 source/target pairs use distinct Unicode code points
(required for per-character substitution to do anything).

### 2. Update the JSON `_notes` field

The current `_notes` claims "1949 Tōyō and post-1981 Jōyō" scope; that
has been false since the second pass added 鴎/鴬/鯵/屏/etc. Rewrite to:
"1949 Tōyō, post-1981 Jōyō, and selected 2000 表外漢字字体表 hyōgai
simplifications." Keep the rest (ambiguous-entry rule, classical-sense
limitation, extensibility statement).

### 3. Pin the new entries against regression

Append a "Fourth-pass audit additions (hyōgai 表外漢字字体表 …):" block
to `_PINNED_ENTRIES` in `tests/test_japanese.py`. This is the same
regression-guard mechanism used by the prior three passes.

### 4. Add converter spot-checks

Extend `test_to_kyujitai_newly_added_entries` with eight realistic
contexts: `蝋燭`, `石鹸`, `飛騨`, `刺繍`, `醤油`, `撹拌`, `任侠`,
`桧舞台`. The pinned-entries regression test covers the remaining 11
entries.

## Critical files

- `tutor/data/shinjitai_kyujitai.json` — +19 entries; `_notes`
  rewritten.
- `tests/test_japanese.py` — `_PINNED_ENTRIES` gains 19 pairs;
  `test_to_kyujitai_newly_added_entries` gains 8 spot-checks.

Functions reused unchanged:

- `to_kyujitai_template` (`tutor/japanese.py`) — picks up the new
  entries automatically.
- `relevant_kyujitai_mappings` (`tutor/japanese.py`) — same.
- `build_system_prompt` (`tutor/prompts.py`) — already wires both
  bullets through GROUND TRUTH; no code change.

## Out of scope

- **表外漢字字体表 entries whose 印刷標準字体 shares a Unicode code
  point** with the conventional form — glyph-only variation, not
  addressable by per-character substitution.
- **Broader pre-war simplifications** (e.g. 滬→濾, 麿→麻呂) — user
  chose "official list + a few extras", not a broad sweep.

## Verification

1. `uv run --frozen pytest -q` — all green, including new spot checks
   and the expanded pinned-entries regression guard.
2. `make lint` — clean (ruff + basedpyright + xenon).
3. JSON-load sanity:
   `uv run --frozen python -c "from tutor.japanese import _TABLE;
   [print(c, _TABLE[c]) for c in '唖焔噛侠躯鹸麹桧醤蝋砿蕊騨弯繍撹諌凛篭']"`
   — prints all 19 new pairs.
4. Manual smoke test: feed a Japanese subtitle containing 蝋燭, 石鹸,
   飛騨, 刺繍, 醤油, 撹拌, 桧舞台, 任侠. Confirm the 🔁 Variant row
   rewrites each and matching vocab items render in `shinjitai /
   kyūjitai (kana, IPA) → translation`. Sanity: Chinese, Korean,
   English sources unchanged.
