# Fix `[Errno 7] Argument list too long` when opening a thread

## Context

When opening a followup thread in the web UI, the thread pool calls
`ClaudeSDKClient(options=ClaudeAgentOptions(system_prompt=<str>, ...))`.
The SDK 0.1.63 transport embeds that string directly into the argv of
the bundled `claude` subprocess
(`claude_agent_sdk/_internal/transport/subprocess_cli.py` lines 207–212):

```python
cmd.extend(["--system-prompt", self._options.system_prompt])
```

Linux's `execve(2)` caps **each individual argument string** at
`MAX_ARG_STRLEN = PAGE_SIZE * 32 = 128 KiB`. (Confirmed locally:
`getconf PAGE_SIZE` → 4096.) The total `ARG_MAX` is 2 MiB, but the
per-arg ceiling is what we hit.

`build_thread_system_prompt` (`tutor/prompts.py:83-122`) embeds up to 100
prior dialog entries with their full explanations
(`tutor/thread_pool.py:96-104`). Each explanation is ~100 words, and long
raw lines stack on top. With a handful of beefy entries the rendered
prompt sails past 128 KiB, `execve` fails with `E2BIG`, and the SDK
surfaces it as the `[Errno 7] Argument list too long` we see.

`--extra-system-prompt` on the main session (`build_system_prompt` at
`tutor/prompts.py:64-80`) has the same latent failure mode if the user
supplies a large file, but that's static at startup and failing loudly
is fine.

**Intended outcome:** thread prompts get trimmed down to a safe byte
budget before they reach the SDK, so threads open reliably regardless of
how long prior explanations are. The main-session prompt gets a clear
startup check so an oversized `--extra-system-prompt` is caught early.

## Approach

Cap system-prompt byte length in `tutor/prompts.py`. No SDK-level
changes, no file-based hand-off, no new directories or lifecycle logic.

Constant:

```python
# Linux execve() per-arg cap is PAGE_SIZE * 32 = 128 KiB on x86_64.
# Stay well under with a safety margin — the SDK adds a little framing,
# and multi-byte UTF-8 can surprise naive byte counts.
MAX_SYSTEM_PROMPT_BYTES = 96 * 1024
```

### 1. Trim thread prompts to fit

Modify `build_thread_system_prompt` (`tutor/prompts.py:83-122`) to drop
the oldest `context_lines` entries until the rendered prompt fits
`MAX_SYSTEM_PROMPT_BYTES`. The anchor line is never dropped (it's the
thing the learner is asking about). The context window is already
ordered oldest→newest, so trimming from the front preserves the most
recent (most relevant) context.

Shape:

```python
def build_thread_system_prompt(
    source_language: str,
    target_language: str,
    level: str,
    anchor: LineRecord,
    context_lines: list[LineRecord],
) -> str:
    trimmed = list(context_lines)
    while True:
        prompt = _render_thread_system_prompt(
            source_language, target_language, level, anchor, trimmed,
        )
        if len(prompt.encode('utf-8')) <= MAX_SYSTEM_PROMPT_BYTES:
            return prompt
        if not trimmed:
            # Anchor alone already exceeds the budget — truncate the
            # anchor explanation rather than fail. An overlong anchor
            # explanation is an unusual input (the explainer is capped
            # at ~100 words per prompts.py:41) but we don't want the
            # thread to be un-openable.
            return _render_thread_system_prompt(
                source_language,
                target_language,
                level,
                _truncate_anchor(anchor, MAX_SYSTEM_PROMPT_BYTES),
                [],
            )
        trimmed.pop(0)
```

Factor out the existing string-build body into a private
`_render_thread_system_prompt(...)` helper (same signature, just returns
the string) so the loop can call it repeatedly. The rendering logic
itself is unchanged from the current lines 91–122.

`_truncate_anchor` is a tiny helper: if
`len(anchor.explanation.encode()) > N`, return a new `LineRecord` with
the explanation byte-sliced to N bytes and `"…"` appended (careful to
cut on a UTF-8 boundary — `encode()[:N].decode('utf-8', errors='ignore')`).

### 2. Fail fast on oversized main prompt

Modify `build_system_prompt` (`tutor/prompts.py:64-80`). After producing
the final string (base + optional extra), check the byte length and
raise `SystemExit` with an actionable message if it exceeds the budget:

```python
result = base + '\n\nADDITIONAL SOURCE-SPECIFIC CONTEXT:\n\n' + extra
if len(result.encode('utf-8')) > MAX_SYSTEM_PROMPT_BYTES:
    msg = (
        f'oh-language-tutor: system prompt is {len(result.encode("utf-8")):,} '
        f'bytes but the Linux execve per-arg cap limits it to '
        f'{MAX_SYSTEM_PROMPT_BYTES:,} bytes. Shorten '
        f'--extra-system-prompt ({args.extra_system_prompt}).'
    )
    raise SystemExit(msg)
return result
```

This matches the existing `SystemExit` pattern a few lines above in the
same function.

### 3. Nothing else changes

- `tutor/thread_pool.py` — unchanged. `_connect` keeps passing the
  string `system_prompt` directly; the string is now guaranteed small
  enough.
- `tutor/web.py`, `tutor/terminal.py`, `tutor/tui.py` — unchanged.
- `tutor/replay.py` — unchanged. The replay preamble is sent as a user
  message (`fresh_client.query(preamble)`), which goes over the SDK's
  stdin/JSON channel, not argv — not affected by `MAX_ARG_STRLEN`.

## Critical files

- `tutor/prompts.py` — add `MAX_SYSTEM_PROMPT_BYTES`, add a renderer
  helper, add trimming loop in `build_thread_system_prompt`, add the
  guard in `build_system_prompt`.

## Verification

1. Type-check: `uv run --frozen basedpyright tutor/`.
2. Lint: `uv run --frozen ruff check tutor/`.
3. Tests: `uv run --frozen pytest` (plus a new unit test that
   constructs 200 synthetic `LineRecord`s each with a 2000-byte
   explanation, calls `build_thread_system_prompt`, and asserts the
   result's UTF-8 byte length is ≤ `MAX_SYSTEM_PROMPT_BYTES`).
4. Manual reproduction of the original failure:
   - Start the web UI against a `state_dir` whose `tutor.json` already
     contains ~100 entries with long explanations (the user's own
     state dir from the bug report, if still available).
   - Click a line late in the stream to open a thread — the one that
     previously failed with `tutor_thread_20260418034204_89006fdc`.
   - Confirm it connects and streams a reply.
5. Smoke-check the main-session guard: point `--extra-system-prompt` at
   a file > 96 KiB and confirm the CLI exits with the clear error
   message from step 2, rather than a later cryptic `Errno 7`.
