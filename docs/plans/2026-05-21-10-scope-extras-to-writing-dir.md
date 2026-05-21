# Scope the extra system prompt to the writing state dir

## Context

`--extra-system-prompt` is loaded once at startup and stored on
`WebContext.extras_text` (`tutor/web.py:631`, `:651`). The `/tutor/{dir_name}/commands/explain`
endpoint passes it into `build_system_prompt` unconditionally
(`tutor/web.py:553`), so the extras get appended to the system prompt
for *every* viewing dir — including sibling dirs the user opens via the
picker that have nothing to do with the dataset the operator launched
the process for.

The `--extra-system-prompt` flag is conceptually a per-dataset override
(e.g. show notes for a specific show, glossary for a specific book).
The dataset that flag is paired with is the one named by `--state-dir`
— that's the dir stdin writes to (`ctx.writing_dir`, set at
`tutor/web.py:633`). All other dirs the user may browse to are
unrelated, so they should fall back to the base prompt.

## Approach

Gate the extras at the explain endpoint so they are included only when
the resolved viewing session's `state_dir` matches `ctx.writing_dir`.
`ctx.writing_dir` is already resolved with `.resolve()` at startup
(`tutor/web.py:633`), and `_get_or_create_session` keys sessions by
`state_dir.resolve()` (`tutor/web.py:238`), so `session.state_dir ==
ctx.writing_dir` is a sound equality check.

This is a one-call-site change because:

- `extras_text` only flows into `build_system_prompt`, which is only
  invoked from the explain endpoint (verified by `grep
  build_system_prompt tutor/`).
- Followup/ask threads don't consume `extras_text` today, so they
  remain unaffected.

## Files to change

- `tutor/web.py` — in the `explain` route (around line 549), replace
  the unconditional `ctx.extras_text` argument with:

  ```python
  extras = ctx.extras_text if session.state_dir == ctx.writing_dir else None
  ```

  and pass `extras` into `build_system_prompt`. Update the field
  comment on `WebContext.extras_text` (line 137) to reflect that it is
  scoped to the writing dir.

- `tests/test_web.py` — add a test that opens a non-writing sibling
  dir, hits its explain endpoint with `extras_text` set on the
  context, and asserts the extras are NOT in the system prompt the
  fake Claude client receives. Mirror the existing
  `test_post_explain_oversized_extras_returns_400` pattern for setup
  (`tests/test_web.py:888`), and capture the system prompt via the
  existing `FakeClaudeSDKClient` infrastructure already used
  elsewhere in the file. Also add a positive test confirming the
  writing dir still gets the extras.

## Verification

1. `make lint` and `uv run --frozen pytest tests/test_web.py
   tests/test_prompts.py` — both must pass.
2. Manual: launch the app with `--state-dir state/foo
   --extra-system-prompt some.txt`, create a sibling `state/bar`,
   trigger Explain in `foo` and confirm via `tutor.log` that the
   system prompt contains the `ADDITIONAL SOURCE-SPECIFIC CONTEXT`
   block; switch to `bar` via the picker, trigger Explain, and
   confirm the block is absent.
