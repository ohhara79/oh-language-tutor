# Auto-fallback with history replay on resume failure

## Context

When a Claude session resume fails, the tutor currently has no graceful recovery:

- **Process restart:** The exception from `ClaudeSDKClient.__aenter__()` propagates through `main.py:33`'s `asyncio.run()` and crashes the app. `state/session.id` is left stale, so the next launch retries the same bad ID.
- **Thread reopen:** The lazy connect in `tutor/thread_pool.py:144` catches the exception but only emits an `on_error` and drops the user's first message. The thread stays open showing cached history, but the user cannot send anything.

Both cases have enough on-disk data to reconstruct context: `state/tutor.json` is an append-only `(raw, explanation)` log of every main-pane turn, and `state/threads/<id>.json` holds all thread messages. Goal: catch the resume failure, start a fresh session, and replay the most recent turns as a synthesized preamble so Claude has continuity.

Decisions agreed with user:
- Fully automatic fallback (no `--no-replay` flag, no user prompt).
- Cap replay at the last **100 turns** via `REPLAY_MAX_TURNS`.
- Mechanism: synthesized **preamble message** as a single `client.query(...)` call (the SDK has no assistant-message injection).
- Emit a brief notice on fallback, kept in one place so removing the whole feature later is trivial.

## SDK constraint

`ClaudeAgentOptions` (`claude_agent_sdk`) exposes only `resume: str | None`, `fork_session: bool`, `system_prompt`, `continue_conversation`, and `extra_args`. There is no `messages` / `initial_messages` / assistant-injection API. `ClaudeSDKClient.query()` sends only user text. So "replay" is implemented by concatenating past turns into one synthetic user message and draining the response.

## Design

### New module `tutor/replay.py`

Single-responsibility module — delete this file plus its callers to remove the feature.

- `REPLAY_MAX_TURNS = 100`
- `build_preamble(turns: list[tuple[str, str]]) -> str` — takes `(user, assistant)` pairs (caller pre-trims), returns:
  ```
  Here is our prior conversation. Please continue from where we left off.

  User: …
  Assistant: …
  …

  (continue from here)
  ```
- `pairs_from_thread(messages: list[ThreadMessage]) -> list[tuple[str, str]]` — pair alternating user/assistant messages; drop an unmatched trailing user. No trimming (caller slices to `REPLAY_MAX_TURNS`).
- `notify_fallback(log, sink, *, total, replayed)` — single place that writes `=== resume failed; replayed {replayed}/{total} turns into a new session ===` to the session log and calls `sink.on_error(msg)`.
- `connect_with_fallback(primary, *, fresh, tutor_entries, sink, log) -> ClaudeSDKClient` — attempts `ClaudeSDKClient(primary).__aenter__()`; on failure retries with `fresh`, replays last `REPLAY_MAX_TURNS` of `tutor_entries` as a preamble, and emits the notice. If `primary.resume is None`, any failure is raised (no fallback).

### Main-session path (process restart)

Call sites:
- `tutor/terminal.py` — `run_terminal`
- `tutor/gui.py` — `OhLanguageTutorApp.launch`

Each now:
1. Builds both `options` (with `resume=resume_id`) and `options_fresh` (with `resume=None`).
2. Calls `client = await connect_with_fallback(options, fresh=options_fresh, tutor_entries=TutorStore(...).load() if resume_id else [], sink=sink, log=log)`.
3. Runs the existing loop in a `try` and calls `await client.__aexit__(None, None, None)` in `finally`.

The existing `stdin_loop` saves the new session ID on the next real `ResultMessage` (`tutor/core.py:109-114`) — no change needed there.

### Thread-reopen path

Call site: `tutor/thread_pool.py` — `send_message`, lazy connect block.

Extended try/except shape:

1. Try `_connect(at.system_prompt, at.resume_session_id)` (unchanged).
2. On exception: if `at.resume_session_id is None`, emit the existing error and return (unchanged behaviour).
3. Otherwise retry `_connect('', None)` — mirrors the empty-system-prompt convention already used on reopen; if the retry raises, emit error and return.
4. Build `pairs = pairs_from_thread(at.meta.messages)[-REPLAY_MAX_TURNS:]`. If non-empty: `await at.client.query(build_preamble(pairs))` and drain `receive_response()` (seed failures are logged via `on_error` and return).
5. Call `notify_fallback(...)` and clear `at.resume_session_id` so the active thread knows it recovered.

The new session ID lands in `at.meta.session_id` via the existing `ResultMessage` handling in `_stream_response` (line 235), and is persisted by `_store.save_thread(at.meta)` on the next assistant turn.

### Easy-to-remove shape

- All fallback-related behaviour imported from `tutor.replay`.
- Removal recipe: delete `tutor/replay.py`, then `git grep 'tutor.replay'` — each hit is a short block whose surrounding try/except collapses back to the original `async with`/`on_error`.

## Critical files

- `tutor/replay.py` — **new**.
- `tutor/terminal.py` — fallback-aware connect.
- `tutor/gui.py` — fallback-aware connect.
- `tutor/thread_pool.py` — extended try/except in `send_message`.
- `tutor/tutor_store.py:19` — reuse `TutorStore.load()` (unchanged).

## Verification

End-to-end manual checks (requires launching the app):

1. **Main session fallback (terminal and GUI):**
   - Write a bogus session ID: `uuidgen > state/session.id`.
   - Launch tutor; expect no crash; stderr (terminal) or status bar (GUI) shows `resume failed; replayed N/M turns into a new session`; the next user line produces a response that references earlier tutor context.
   - Confirm `state/session.id` is updated to the new ID after the first reply.

2. **Thread reopen fallback:**
   - In `state/threads/<id>.json`, replace `session_id` with a bogus UUID.
   - Launch GUI, reopen the thread, send a followup.
   - Expect status bar fallback notice, successful reply that references prior thread turns, and updated `session_id` in the thread JSON.

3. **Truncation path:**
   - With a `tutor.json` containing >100 entries, trigger a main-session fallback and confirm the notice reports `replayed 100/<total>`.

4. **Static checks:**
   - `uv run --frozen basedpyright` — must pass (currently 0 errors).
   - `uv run --frozen ruff check tutor/` — must pass.
