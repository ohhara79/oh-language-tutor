#!/bin/bash

if [ -z "$1" ]; then
    echo "usage: $0 <path/to/file.ass> [segment]" >&2
    echo "  segment: 1-based index of the \\N-separated text segment to keep (default: 1)" >&2
    exit 1
fi

ass="$1"
segment="${2:-1}"

if [ ! -f "$ass" ]; then
    echo "error: ass file not found: $ass" >&2
    exit 1
fi

state_dir="state/$(basename "$ass" .ass)"

if [ -d "$state_dir" ]; then
    uv run --frozen --no-dev main.py --state-dir "$state_dir" < /dev/null
else
    bom=$(head -c 3 "$ass" | xxd -p | tr -d '\n')
    case "$bom" in
        fffe*|feff*) iconv -f UTF-16 -t UTF-8 "$ass" ;;
        efbbbf)      tail -c +4 "$ass" ;;
        *)           cat "$ass" ;;
    esac | \
    tr -d '\r' | \
    awk -v seg="$segment" -F',' '
        /^Dialogue:/ {
            text = $10
            for (i = 11; i <= NF; i++) text = text "," $i
            gsub(/\{[^}]*\}/, "", text)
            n = split(text, parts, /\\N/)
            if (seg <= n) {
                line = parts[seg]
                gsub(/\\r/, "", line)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
                if (length(line) > 0) print line
            }
        }
    ' | \
        uv run --frozen --no-dev main.py --state-dir "$state_dir"
fi
