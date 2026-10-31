# Update claude-agent-sdk to 0.2.176 and default both models to Opus 5.5

## Context

`pyproject.toml` pinned `claude-agent-sdk==0.2.139` (bumped 2026-08-15 in
`2026-08-15-01-update-agent-sdk-and-opus-5.md`); PyPI's latest is now
`0.2.176`. Both `--explain-model` and `--ask-model` defaulted to
`claude-opus-5`; the current Opus is Opus 5.5 (`claude-opus-5-5`). Same shape
as the previous bump: move the pin and the model defaults together.

## Change

1. `pyproject.toml:8` — `claude-agent-sdk==0.2.139` → `==0.2.176`; refresh
   `uv.lock`. The new version adds one transitive dependency, `jsonschema`.
2. `tutor/args.py:10-11` — `DEFAULT_EXPLAIN_MODEL` and `DEFAULT_ASK_MODEL`
   `'claude-opus-5'` → `'claude-opus-5-5'`.
3. `README.md:71-72` — update both default cells in the CLI flags table.

No call-site changes. The fields passed to `ClaudeAgentOptions`
(`tutor/web.py`, `tutor/thread_pool.py`: `system_prompt`, `model`,
`allowed_tools`, `resume`, `include_partial_messages`) all still exist in
0.2.176, and the imports (`ClaudeSDKClient`, `AssistantMessage`,
`ResultMessage`, `StreamEvent`, `TextBlock`) still resolve.
`tests/test_args.py` references the constants by name, so no test edit.

## Verification

- `uv sync` — lockfile resolves with the new pin.
- `uv run --frozen python -c "import dataclasses; from claude_agent_sdk
  import ClaudeAgentOptions; print(sorted(f.name for f in
  dataclasses.fields(ClaudeAgentOptions)))"` — the five fields above survive.
- `make lint` — clean.
- `uv run --frozen pytest` — all pass.
