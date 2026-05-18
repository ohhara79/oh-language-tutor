# Add SAMI (.smi) subtitle parser

## Context

`scripts/srt.sh` and `scripts/ass.sh` ingest subtitle files into `main.py` via a shell pipeline that emits one cue per line. SAMI (`.smi`) is the third format in this collection and the sample `프렌즈.S01E01.smi` is a Korean Friends S01E01 SAMI file in CP949 with no BOM. `file(1)` misidentifies it as ISO-8859 and UTF-8 decode fails at byte 0xbe.

SAMI files in the wild span CP949/EUC-KR (Korean), Shift_JIS/CP932 (Japanese), GBK/Big5/GB18030 (Chinese), UTF-8 (modern), and occasionally UTF-16. The BOM-only probe used by `ass.sh:22-26` cannot cover the legacy CJK cases. Rather than pull in `chardet` for heuristic detection (which can mis-guess on short or single-language files), the parser fails loudly when neither BOM nor strict-UTF-8 succeeds and asks the user to pass `--encoding`. Predictable beats clever.

## Approach

New `scripts/smi.sh` (bash, executable):

- **Args**: positional `<file.smi>`, plus optional `--class CLASS` and `--encoding ENC`.
- **State-dir resume** identical to `srt.sh:14-20` / `ass.sh:17-20`: if `state/$(basename .smi)` exists, skip ingestion and reopen the session.
- **Encoding cascade** (cold path only): `--encoding` override → BOM probe (UTF-16 LE/BE via `iconv -f UTF-16`, UTF-8 BOM via `tail -c +4`) → strict UTF-8 try (`iconv -f UTF-8 -t UTF-8 > /dev/null`) → fail with an error that names common CJK candidates.
- **Body pipeline**: `iconv -f $enc -t UTF-8 | tr -d '\r' | awk … | uv run --frozen --no-dev main.py --state-dir …`.
- **awk parser**: single pass, buffered. Treats each `<SYNC>` as a cue boundary, captures the class from the following `<P Class=…>` (inherits previous on omission), joins multi-line cues with a space, strips remaining tags, decodes common HTML entities (`&nbsp;`, `&#160;`, `&amp;`, `&lt;`, `&gt;`, `&quot;`, `&apos;`), drops empty/`&nbsp;`-only cues. Class filter defaults to the first `Class=` seen if `--class` is absent.

Why `<br>` → space (not newline): `tutor/core.py:21-53` (`stdin_loop`) treats each input line as one `TutorEntry`. Splitting cues at `<br>` would fragment two-line Korean sentences into independently-explained halves. Space-joining matches how `srt.sh:22-26` already collapses multi-line SRT cues.

Downstream dedup and blank-line handling are already done by `stdin_loop`; awk does not need to dedupe.

## Files

- `scripts/smi.sh` — new.
- No changes to `pyproject.toml` or `uv.lock` (no new deps).

## Verification

1. **Failure on undetectable encoding**: `./scripts/smi.sh 프렌즈.S01E01.smi` exits non-zero with a "cannot determine encoding" message that mentions `--encoding`.
2. **Cold run with override**: `./scripts/smi.sh 프렌즈.S01E01.smi --encoding cp949 --class KRCC` creates `state/프렌즈.S01E01/`; first emitted cue is `얘기할 것도 없어 같이 일하는 동료일 뿐야`.
3. **Default class**: `--encoding cp949` without `--class` produces identical output (KRCC is the first body class).
4. **Resume**: rerunning step 2 skips ingestion and reopens against existing state.
5. **BOM path**: a synthesized UTF-8-with-BOM `.smi` is parsed without `--encoding`.
6. **Strict-UTF-8 path**: a synthesized BOM-less UTF-8 `.smi` is parsed without `--encoding`.
7. **`<br>` joining**: a synthesized two-line cue emerges space-joined on one output line.
8. **`&nbsp;`-only cues** are dropped.
9. `bash -n scripts/smi.sh` parses clean; `make lint` is clean.
