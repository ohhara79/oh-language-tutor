# Change default explain model to claude-opus-4-7

## Context

`--explain-model` currently defaults to `claude-sonnet-4-6` while `--ask-model`
already defaults to `claude-opus-4-7`. The user wants the streaming explanation
client to use Opus 4.7 by default as well, so both code paths use the same
strongest model unless overridden on the CLI.

## Change

1. `tutor/args.py:10` — `DEFAULT_EXPLAIN_MODEL = 'claude-sonnet-4-6'` →
   `DEFAULT_EXPLAIN_MODEL = 'claude-opus-4-7'`.
2. `README.md:86` — update the table cell for `--explain-model` default from
   `claude-sonnet-4-6` to `claude-opus-4-7`.

No other call sites hardcode the default; `tests/test_args.py` imports the
constant by name so it continues to pass.

## Verification

- `uv run --frozen pytest tests/test_args.py` — default-args test still asserts
  against the constant.
- `make lint` — confirm clean.
