#!/bin/bash

scummvm 2>&1 | \
    uv run --frozen --no-dev main.py \
        --extra-system-prompt extras/sword1.md \
        --filter-regex '^\w+: "' \
        --state-dir state/sword1 \

