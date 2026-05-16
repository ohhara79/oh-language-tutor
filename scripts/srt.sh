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
