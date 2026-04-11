#!/bin/bash

scummvm 2>&1 | uv run --frozen --no-dev main.py \
            --source-language English \
            --target-language Korean \
            --level intermediate \
            --extra-system-prompt extras/bladerunner.md \
            --filter-regex '^\d+: "'
