# Split explanation and ask-thread models

## Context

Today the tutor uses one CLI flag, `--model`, for both the streaming
explanation client and the follow-up "ask thread" pool. Explanations
are short, latency-sensitive turns where Haiku is plenty; ask-thread
turns are longer, more reasoning-heavy, and benefit from Opus. Forcing
both to the same model means either paying Opus prices for every
glossed line, or accepting Haiku quality on threaded follow-ups.

Goal: let the user pick each model independently, with sensible
defaults — Haiku 4.5 for explanations, Opus 4.7 for ask threads.

Per the "no backwards-compat shims" rule, the existing `--model` flag
is removed (not aliased). Callers must migrate to the two new flags.

## Approach

Replace `--model` with two flags in `tutor/args.py`:

- `--explain-model` — model for the main streaming explanation client.
  Default: `claude-haiku-4-5`.
- `--ask-model` — model for the `FollowupThreadPool` ask-thread client.
  Default: `claude-opus-4-7`.

Update each runner (terminal, tui, web) to:

- Pass `args.explain_model` into the two `ClaudeAgentOptions` blocks
  that drive the main explanation client.
- Pass `args.ask_model` as the `model=` argument to
  `FollowupThreadPool(...)`.
- Update the `=== session start ...` log line to record both models.

`FollowupThreadPool` already accepts `model: str` in its constructor
and threads it through `_connect()` to `ClaudeAgentOptions`, so no
changes are needed inside `tutor/thread_pool.py` or `tutor/core.py`.

## Files to touch

- `tutor/args.py` — drop `DEFAULT_MODEL` and the `--model` arg; add
  `DEFAULT_EXPLAIN_MODEL = 'claude-haiku-4-5'`,
  `DEFAULT_ASK_MODEL = 'claude-opus-4-7'`, and the two new `add_argument`
  calls. Keep help text consistent with the existing style
  (`'Claude model id for ... (default: %(default)s).'`).
- `tutor/terminal.py` — lines 40–51 (both `ClaudeAgentOptions` blocks)
  switch `model=args.model` → `model=args.explain_model`. Update the
  session-start log line at line 62 to log both models.
- `tutor/tui.py` — lines 746–757 (both `ClaudeAgentOptions` blocks)
  switch to `args.explain_model`. Line 774 log line: log both. Line
  789–798 (`FollowupThreadPool(...)`) pass `model=args.ask_model`.
- `tutor/web.py` — lines 276–287 (both `ClaudeAgentOptions` blocks)
  switch to `args.explain_model`. Lines 292–295 log line: log both.
  Lines 309–318 (`FollowupThreadPool(...)`) pass `model=args.ask_model`.
- `README.md` / `AGENTS.md` — if either documents `--model`, update the
  reference. (Spot-check during implementation; don't edit if absent.)

## Non-changes

- `tutor/thread_pool.py` — already takes `model` as a constructor param
  and passes it to `ClaudeAgentOptions` in `_connect()` (line 258). No
  edit needed.
- `tutor/core.py` — receives an already-constructed client; doesn't
  see the model name. No edit needed.
- `tutor/prompts.py` — system-prompt content is model-agnostic. No
  edit needed.

## Verification

1. `make lint` passes (basedpyright + ruff).
2. Help text shows both flags with correct defaults:
   `uv run --frozen python -m main --help` (or equivalent entry) lists
   `--explain-model` defaulting to `claude-haiku-4-5` and `--ask-model`
   defaulting to `claude-opus-4-7`, and no longer lists `--model`.
3. Terminal smoke test — pipe a short stream in with required language
   flags; confirm `state/tutor.log` `=== session start ...` line shows
   both `explain_model=` and `ask_model=` values, and that explanation
   output streams normally.
4. TUI smoke test (`--tui`) — start a thread on a glossed line and
   confirm the follow-up answer streams. The two clients should be
   running on different models; the SDK subprocess command line for
   the ask-thread client should include the Opus id (verify via
   `ps -ef | grep claude` while a thread is active, or by tailing
   `tutor.log`).
5. Web smoke test (`--web`) — same as TUI but through the browser UI.
6. Override smoke test — pass `--explain-model claude-opus-4-7
   --ask-model claude-haiku-4-5` and confirm via the log line that
   both flags are honored (i.e. flags actually plumb through, not just
   defaults).
