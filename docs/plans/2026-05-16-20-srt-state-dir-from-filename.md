# scripts/srt.sh — derive state-dir from filename and skip re-ingest

## Context

`scripts/srt.sh` currently hard-codes `--state-dir state/srt` and passes three
flags that `main.py` no longer accepts (`--source-language`, `--target-language`,
`--level`). Argparse would reject them — confirmed `tutor/args.py` has no such
flags, so the script is broken if you actually try to run it. We want each
`.srt` to land in its own state dir, and re-running on a finished dataset should
open the web UI on the existing data without re-ingesting the subtitles.

## Approach

Rewrite `scripts/srt.sh` so it:

1. Drops `--source-language English --target-language Korean --level intermediate`.
2. Derives `state_dir="state/$(basename "$srt" .srt)"` from the first positional
   arg (matches the `bladerunner.srt` → `state/bladerunner` shape).
3. Branches on `[ -d "$state_dir" ]`:
   - **Exists** → launch `main.py --state-dir "$state_dir"` with stdin closed
     (`< /dev/null`). `main.py` reads stdin via `tutor.core.stdin_loop`
     (`tutor/web.py:670`); closed stdin EOFs immediately and the web server
     comes up against the existing dataset.
   - **Missing** → run the existing cat/tr/sed/awk pipeline into `main.py`,
     passing the derived `--state-dir`. `make_dir_session` creates the dir
     (`tutor/web.py:212`).

Only positional arg `"$1"` is used (replacing `"$*"`) so paths with spaces work
and the basename derivation is unambiguous.

## Files

- `scripts/srt.sh` — rewrite per above. Single file touched.

## Final script shape

```bash
#!/bin/bash

srt="$1"
state_dir="state/$(basename "$srt" .srt)"

if [ -d "$state_dir" ]; then
    uv run --frozen --no-dev main.py --state-dir "$state_dir" < /dev/null
else
    cat "$srt" 2>&1 | \
    tr -d '\r' | \
    sed -e 's|</\?i>||g' | \
    awk 'BEGIN{RS=""; FS="\n"} {
        text=$3
        for (i=4; i<=NF; i++) text = text " " $i
        print text
    }' | \
        uv run --frozen --no-dev main.py --state-dir "$state_dir"
fi
```

## Verification

1. Fresh run: `rm -rf state/bladerunner && scripts/srt.sh bladerunner.srt` —
   confirm `state/bladerunner/` is created and the web UI shows ingested lines.
2. Re-run: `scripts/srt.sh bladerunner.srt` with `state/bladerunner` already
   present — confirm the SRT is NOT re-piped (no new lines appended, mtimes on
   `tutor.log` / `tutor.json` unchanged) and the web UI still opens against the
   existing dataset.
3. `make lint` is unaffected (shell script only).
