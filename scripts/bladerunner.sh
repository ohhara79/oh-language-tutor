#!/bin/bash

scummvm 2>&1 | \
    uv run --frozen --no-dev main.py \
        --extra-system-prompt extras/bladerunner.md \
        --filter-regex '^\w+: "' \
        --state-dir state/bladerunner \

