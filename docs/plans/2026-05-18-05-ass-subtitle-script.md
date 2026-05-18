# Add ASS subtitle support via a shell preprocessor

## Context

The project already ingests SRT subtitles via `scripts/srt.sh`, which preprocesses the file with shell tools and pipes clean text lines to `main.py`. Extend the same workflow to ASS files (Advanced SubStation Alpha). Sample at the repo root: `老友记.S01E01.ass` (Friends S01E01, English + Simplified Chinese).

ASS differs from SRT in three ways the shell script must handle:

1. **Encoding** — the sample is UTF-16LE with a BOM; other ASS files may be UTF-16BE or UTF-8. BOM-based auto-detection.
2. **Structure** — subtitles live on `Dialogue: ...` lines inside the `[Events]` section, with 9 comma-separated header fields before the text field.
3. **Inline formatting** — text contains `{...}` ASS override tags (font, color, position, karaoke, etc.) and `\N`/`\r` line breaks. The sample pairs English and Chinese on a single `Dialogue:` line, joined with `\N`. Keep only one segment per line (specified by an integer index, default 1).

No Python changes required: `tutor/core.py:stdin_loop` (lines 21–53) already ingests any line-separated text from stdin and dedupes consecutive duplicates.

## Approach

Add `scripts/ass.sh`, mirroring `scripts/srt.sh` (state-dir resume pattern, `uv run --frozen --no-dev main.py`, same invocation shape). Optional positional arg `[segment]` selects which `\N`-separated text piece to keep (1-based, default `1`). Pipeline:

1. **Validate input** — usage check + file-exists check (copy from `scripts/srt.sh:3-12`).
2. **Derive state dir** — `state/$(basename "$ass" .ass)` (mirror `srt.sh:14`).
3. **Resume short-circuit** — if `state_dir` exists, launch `main.py --state-dir "$state_dir" < /dev/null` and exit (mirror `srt.sh:16-17`).
4. **Decode to UTF-8** — peek the first 3 bytes with `head -c 3 | xxd -p`; branch:
   - `fffe…` or `feff…` → `iconv -f UTF-16 -t UTF-8` (the `UTF-16` codec consumes the BOM and detects endianness).
   - `efbbbf` → `tail -c +4` (strip UTF-8 BOM).
   - else → `cat` (assume UTF-8).
5. **Strip CR** — `tr -d '\r'`.
6. **Extract chosen segment per Dialogue line** — single `awk -F','` pass:
   - Match `/^Dialogue:/`.
   - Reassemble fields 10..NF into `text` (re-joining with `,` because the text body itself may contain commas).
   - `gsub(/\{[^}]*\}/, "", text)` — strip all `{…}` override blocks.
   - `split(text, parts, /\\N/)` — split on the literal two-char escape `\N`.
   - Print `parts[segment]` after stripping any stray `\r` escapes and trimming whitespace; skip if empty or if the chosen segment doesn't exist on that line.
7. **Pipe to `main.py`** with `--state-dir "$state_dir"` (mirror `srt.sh:27`).
8. `chmod +x scripts/ass.sh`.

## Files

- **New**: `scripts/ass.sh`

No edits to Python or other shell scripts. The `tutor/` package is format-agnostic and needs no changes.

## Verification

1. **Dry-run preprocessing** (no `main.py`): run the decode + awk pipeline on `老友记.S01E01.ass` with `segment=1`. Expect the first non-empty lines to include `The One Where Monica Gets A New Roommate` followed by the English theme-song lyrics. Mono-segment lines like `（主演：詹妮弗·安妮斯顿）` (no `\N`) appear at segment=1.
2. **Segment 2**: re-run with `segment=2`. Expect Chinese counterparts: `六人行 第1季 第01集 莫妮卡的新室友`, `没有人告诉你活着有多累`, etc. Mono-segment lines are skipped.
3. **End-to-end**: `bash scripts/ass.sh 老友记.S01E01.ass`. The web UI opens; lines appear in the left pane.
4. **Resume**: re-run the same command after `state/老友记.S01E01/` exists. Skips preprocessing and reopens existing state.
