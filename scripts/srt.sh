#!/bin/bash

cat "$*" 2>&1 | \
tr -d '\r' | \
sed -e 's|</\?i>||g' | \
awk 'BEGIN{RS=""; FS="\n"} {
    text=$3
    for (i=4; i<=NF; i++) text = text " " $i
    print text
}' | \
    uv run --frozen --no-dev main.py \
        --source-language English \
        --target-language Korean \
        --level intermediate \
        --state-dir state/srt \

