#!/bin/bash

usage() {
    echo "usage: $0 <path/to/file.smi> [--class CLASS] [--encoding ENC]" >&2
    echo "  --class CLASS    SAMI Class attribute to keep (default: first class seen)" >&2
    echo "  --encoding ENC   force input encoding (e.g. cp949, shift_jis, gbk, big5)" >&2
}

if [ -z "$1" ] || [[ "$1" == -* ]]; then
    usage
    exit 1
fi

smi="$1"
shift

user_class=""
user_enc=""

while [ $# -gt 0 ]; do
    case "$1" in
        --class)
            user_class="$2"
            shift 2
            ;;
        --encoding)
            user_enc="$2"
            shift 2
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [ ! -f "$smi" ]; then
    echo "error: smi file not found: $smi" >&2
    exit 1
fi

state_dir="state/$(basename "$smi" .smi)"

if [ -d "$state_dir" ]; then
    uv run --frozen --no-dev main.py --state-dir "$state_dir" < /dev/null
    exit 0
fi

if [ -n "$user_enc" ]; then
    enc="$user_enc"
    strip_bom=0
else
    bom=$(head -c 3 "$smi" | xxd -p | tr -d '\n')
    case "$bom" in
        fffe*)
            enc="UTF-16LE"
            strip_bom=0
            ;;
        feff*)
            enc="UTF-16BE"
            strip_bom=0
            ;;
        efbbbf)
            enc="UTF-8"
            strip_bom=1
            ;;
        *)
            if iconv -f UTF-8 -t UTF-8 "$smi" > /dev/null 2>&1; then
                enc="UTF-8"
                strip_bom=0
            else
                echo "error: cannot determine encoding for $smi (no BOM, not valid UTF-8)." >&2
                echo "       re-run with --encoding ENC, e.g. --encoding cp949 for Korean," >&2
                echo "       shift_jis for Japanese, gbk/big5 for Chinese." >&2
                exit 1
            fi
            ;;
    esac
fi

if [ "$strip_bom" = 1 ]; then
    decode() { tail -c +4 "$smi" | iconv -f "$enc" -t UTF-8; }
else
    decode() { iconv -f "$enc" -t UTF-8 "$smi"; }
fi

decode | \
tr -d '\r' | \
awk -v cls="$user_class" '
    BEGIN {
        want = cls
        cur_class = ""
        cur_text = ""
    }
    function flush(    out) {
        if (cur_class == "") { cur_text = ""; return }
        if (cur_text == "") return
        out = cur_text
        gsub(/<[Bb][Rr][[:space:]]*\/?>/, " ", out)
        gsub(/<[^>]+>/, "", out)
        gsub(/&nbsp;/, " ", out)
        gsub(/&#160;/, " ", out)
        gsub(/&lt;/, "<", out)
        gsub(/&gt;/, ">", out)
        gsub(/&quot;/, "\"", out)
        gsub(/&apos;/, "'\''", out)
        gsub(/&amp;/, "\\&", out)
        gsub(/[[:space:]]+/, " ", out)
        sub(/^ /, "", out)
        sub(/ $/, "", out)
        if (out == "") return
        if (want == "") want = cur_class
        if (cur_class == want) print out
    }
    /<[Ss][Yy][Nn][Cc][[:space:]]/ {
        flush()
        cur_text = ""
        line = $0
        if (match(line, /<[Pp][[:space:]]+[Cc][Ll][Aa][Ss][Ss]=[A-Za-z0-9_]+/)) {
            seg = substr(line, RSTART, RLENGTH)
            sub(/.*[Cc][Ll][Aa][Ss][Ss]=/, "", seg)
            cur_class = seg
        }
        sub(/.*<[Pp][^>]*>/, "", line)
        sub(/.*<[Ss][Yy][Nn][Cc][^>]*>/, "", line)
        cur_text = line
        next
    }
    {
        if (cur_text == "") cur_text = $0
        else cur_text = cur_text " " $0
    }
    END { flush() }
' | \
    uv run --frozen --no-dev main.py --state-dir "$state_dir"
