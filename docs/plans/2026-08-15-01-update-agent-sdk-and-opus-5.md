# Update claude-agent-sdk to 0.2.139 and default both models to Opus 5

## Context

`pyproject.toml` pins `claude-agent-sdk==0.1.63`, published in April; the SDK
has since moved to the 0.2 line. Separately, `--explain-model` and
`--ask-model` both default to `claude-opus-4-7`, which is no longer the
current Opus. Opus 5 is a drop-in at the same list price, so the two moves
belong together: pick up the current harness and the current model in one
step rather than leaving the pin to drift further.

A 0.1 → 0.2 bump on a 0.x package can break, so the SDK surface this project
actually touches has to be checked rather than assumed.

## Change

1. `pyproject.toml:8` — `claude-agent-sdk==0.1.63` →
   `claude-agent-sdk==0.2.139`; refresh `uv.lock`. The 0.2 line adds one
   transitive dependency, `sniffio`.
2. `tutor/args.py:10-11` — `DEFAULT_EXPLAIN_MODEL` and `DEFAULT_ASK_MODEL`
   `'claude-opus-4-7'` → `'claude-opus-5'`.
3. `README.md:71-72` — update the default cells for both flags in the CLI
   flags table.

No call-site changes are expected. The two `ClaudeAgentOptions` constructions
(`tutor/web.py:552`, `tutor/thread_pool.py:277`) pass only `system_prompt`,
`model`, `allowed_tools`, `resume`, and `include_partial_messages`; confirm
each is still a field on the 0.2.139 dataclass, and that
`tutor/thread_pool.py`, `tutor/web.py`, `tutor/stream_util.py`, and
`tests/conftest.py` still resolve their imports (`ClaudeSDKClient`,
`AssistantMessage`, `ResultMessage`, `StreamEvent`, `TextBlock`).
`tests/test_args.py` asserts against the constants by name, so it needs no
edit.

## Verification

- `uv sync` — lockfile resolves with the new pin.
- `uv run --frozen python -c "import dataclasses; from claude_agent_sdk
  import ClaudeAgentOptions; print(sorted(f.name for f in
  dataclasses.fields(ClaudeAgentOptions)))"` — confirm the five fields above
  survive the bump.
- `make lint` — ruff format, ruff check, basedpyright, xenon all clean.
- `uv run --frozen pytest` — 271 pass. The 4 `open_state_dir` failures in
  `tests/test_web.py` are pre-existing (the route is missing from
  `tutor/web.py`) and out of scope here; confirm the count is unchanged
  against the previous commit rather than treating them as a regression.
- Smoke run: start web mode, explain one line, open a follow-up thread, and
  check the session-start log line reports
  `explain_model=claude-opus-5 ask_model=claude-opus-5`.

## Follow-up

0.2.139 exposes `effort`, `thinking`, `task_budget`, `max_budget_usd`, and
`fallback_model` on `ClaudeAgentOptions`. Opus 5 thinks by default, which can
add latency before the first streamed token; if explanations feel slower than
they did on 4.7, `effort` is the lever. Out of scope for this change.
