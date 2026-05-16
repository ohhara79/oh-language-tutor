# Add missing-file guard to scripts/srt.sh

## Context

`scripts/srt.sh` takes an srt path as `$1` and either resumes from `state/<basename>` or pipes the srt through `awk` into `main.py`. Today it never validates `$1`: if the argument is missing or the file does not exist, `basename` produces a misleading `state_dir`, and the resume branch silently re-runs an unrelated session while the fresh-run branch fails deep inside the pipeline with a confusing `cat` error. A user just hit this and asked for an explicit early failure.

## Change

Add a guard immediately after the shebang in `scripts/srt.sh:1`:

- If `$1` is empty, print a usage message to stderr and exit non-zero.
- If `$1` is set but the file does not exist (`! -f "$1"`), print an error naming the missing path to stderr and exit non-zero.

Keep the rest of the script untouched — the resume-from-state branch keeps working because the `-f` check confirms the srt file is present even when we end up using `state_dir`.

Suggested shape:

```bash
#!/bin/bash

if [ -z "$1" ]; then
    echo "usage: $0 <path/to/file.srt>" >&2
    exit 1
fi

srt="$1"
if [ ! -f "$srt" ]; then
    echo "error: srt file not found: $srt" >&2
    exit 1
fi

state_dir="state/$(basename "$srt" .srt)"
# ... rest unchanged
```

## Files

- `scripts/srt.sh` — only file modified.

## Verification

- `bash scripts/srt.sh` → exits non-zero, prints usage line.
- `bash scripts/srt.sh /tmp/does-not-exist.srt` → exits non-zero, prints "srt file not found" with the path.
- `bash scripts/srt.sh <an-existing-srt>` → behaves exactly as before (either resumes from `state/<basename>` or streams through `awk` into `main.py`).
- `make lint` is a no-op for shell, but run it to confirm nothing else regressed.
