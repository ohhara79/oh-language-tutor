# Raise pytest coverage from 84% to 96%

## Context

`make test --cov` reported overall coverage of **84%** with several modules under-tested:

| Module | Before | Notable gaps |
|---|---|---|
| `tutor/thread_pool.py` | 71% | `hide_when_idle`, `clear_tutor_entry_explanation`, hide-with-active-task, resume/retry failures, query-failure error path, `_on_task_done` error case |
| `tutor/web.py` | 77% | `/partials/older`, `/commands/clear_explanation`, `_make_lazy_log`, `make_dir_session`, `_get_or_create_session`, `_close_session`, cookie defense edges, `LazyLog.flush`/`close`, events ping branch, `open_thread` no-meta 500, PromptTooLargeError handling |
| `tutor/tutor_store.py` | 81% | `clear_explanation_async`, `load_before`, `load_tail` edge cases |
| `tutor/web_sink.py` | 96% | `on_explain_chunk`, `on_explain_aborted`, `on_entry_explanation_cleared`, `flush_pending_writes` empty path |
| `tutor/prompts.py` | 98% | `_render_thread_system_prompt` anchor-without-explanation branch |

The gaps were ordinary behaviors with cheap, deterministic tests available — not the genuinely-hard ones (server bootstrap, 2-second timeout races, post-rename FileNotFoundError). Goal: cover what's testable with the existing fixtures (`FakeClaudeSDKClient`, `FakeClaudeSDKClientFactory`, Jinja env, ASGI transport) and push the project total to ≥95%.

## Approach

Extend the existing per-module test files; do not add new fixtures or test files. Reuse `RecordingSink`, `_pool`, `_build_ctx`, `_make_session`, and the SDK fakes already established.

### `tests/test_tutor_store.py`

- `clear_explanation_async` — clears `explanation` + audience triple, returns `True` for known, `False` for unknown.
- `load_before` — middle cursor with `has_more=True`; cursor near start with `has_more=False`; first entry returns `[]`; unknown cursor returns `None`.
- `load_tail` — `n=0` → `([], False)`; `n < total` → tail with `has_more=True`; `n > total` → all with `has_more=False`.
- `load` — repeated reads return distinct lists (stat cache returns a copy).

### `tests/test_web_sink.py`

- `on_explain_chunk` — broadcasts an OOB `<span>` targeting `#explain-stream-{id}`, HTML-escapes the chunk.
- `on_explain_aborted` — emits the unexplained variant with `hx-swap-oob="outerHTML"`.
- `on_entry_explanation_cleared` — same OOB swap shape.
- `flush_pending_writes` — early-return when no tasks outstanding.
- `track_explain` — done-callback removes the task from `_pending_explains`.

### `tests/test_thread_pool.py`

- `hide_when_idle` — unknown thread no-ops; no-task path falls through to `hide_thread`; in-flight task marks `hide_pending` and the `finally` block tears the thread down after streaming completes.
- `clear_tutor_entry_explanation` — empty `anchor_id` no-ops; happy path cascade-closes threads + clears entry + emits `on_entry_explanation_cleared`; unknown entry emits nothing.
- `send_message` query failure — emits error + `on_thread_done('', '')`.
- `send_message` resume failure → retry connect also fails — emits error + done.
- `send_message` resume failure → preamble query fails — emits `thread replay failed` + done.
- `send_message` two back-to-back messages — second waits on first inside the task; both replies persist in order.
- `hide_thread` with in-flight task — `await asyncio.wait_for(asyncio.shield(at.task), 2.0)` path runs cleanly; client `__aexit__` called.
- `close_all` with in-flight task — drains tasks.
- `_on_task_done` — surfaces non-Cancelled exceptions via `sink.on_error`; ignores `CancelledError`. Invoked directly with finished tasks (the streaming task's own try/except swallows exceptions, so the callback's error branch isn't reachable through `_stream_response`).

### `tests/test_web.py`

- `thread_heading` skips a leading assistant message and finds the later user line (covers the `162->161` branch).
- `_make_lazy_log` — emits the args-flavored header on first write.
- `make_dir_session` — creates the dir, wires components, leaves the log unopened.
- `_get_or_create_session` — cache hit returns the same `DirSession`; cache miss creates and stores one.
- `_close_session` — skips end banner when log unopened; writes banner when opened. Requires `close_all` on the test's `_FakePool`.
- `LazyLog.flush`/`close` — both are no-ops before first write; subsequent flush works; multiple writes share one handle.
- `/partials/older` — happy path, unknown cursor 404, no-cookie 400.
- `/commands/clear_explanation` — 204 + pool call recorded (uses a new `clear_tutor_entry_explanation` method on `_FakePool`); no-cookie 400.
- `/commands/explain` with oversized `extras_text` — 400 with `execve per-arg cap` in the body.
- `/threads/{id}` already-active — skips `reopen_thread`.
- `/commands/open_thread` when pool fails to register meta — returns 500.
- Cookie defenses — dot-prefix and `/`-containing values redirect to the picker.
- `/events` idle ping — drive `asyncio.wait_for` to raise `TimeoutError` so the loop emits `: ping`, then set `stop_event` to exit; assert no initial `thread_list` frame when the fake pool has no threads.

### `tests/test_prompts.py`

- `_render_thread_system_prompt` with `anchor.explanation=None` — covers the line-108 branch (no `[explanation: …]` trailer after the anchor).

## Critical files

- **Edit** `tests/test_tutor_store.py` (+10 tests)
- **Edit** `tests/test_web_sink.py` (+5 tests)
- **Edit** `tests/test_thread_pool.py` (+12 tests)
- **Edit** `tests/test_web.py` (+19 tests; extend `_FakePool` with `clear_tutor_entry_explanation` and `close_all`)
- **Edit** `tests/test_prompts.py` (+1 test)

No production source touched; no new fixtures or test files.

## Verification

1. `make test` — 154 → **206** tests pass.
2. `uv run --frozen pytest --cov=tutor`:
   - `tutor/prompts.py` 98% → **100%**
   - `tutor/web_sink.py` 96% → **100%**
   - `tutor/tutor_store.py` 81% → **97%**
   - `tutor/thread_pool.py` 71% → **97%**
   - `tutor/web.py` 77% → **90%**
   - **Project total 84% → 96%**
3. `make lint` — ruff format, ruff check, basedpyright, and xenon all clean. One per-line `# noqa: ASYNC109` on the fake-`wait_for` signature in `test_events_emits_ping_on_idle_then_exits`; the parameter must exist to satisfy the real call site's keyword.

## Out of scope

Deliberately uncovered residue, all expensive-to-test for marginal coverage:

- `tutor/web.py:639-711` — `run_web` server bootstrap (uvicorn + signal handlers).
- `tutor/thread_pool.py:177-180` — 2-second `wait_for` cancel inside `hide_thread`; the timing branch only fires when the inner task genuinely hangs.
- `tutor/tutor_store.py:199-202` — `stat()` after `rename()` raises `FileNotFoundError`; requires a concurrent unlink race we don't simulate.
- A handful of branch-only misses inside `_stream_response`'s message-loop dispatch (`StreamEvent` vs `AssistantMessage` vs `ResultMessage` alternations) and `_stream_explain`'s parallel.
