# Lift pytest coverage into core / replay / sink / web_sink / thread_pool / terminal / web

## Context

Plan `2026-04-18-16-add-pytest-suite.md` seeded the test harness but explicitly excluded every module that touches `claude_agent_sdk`, a TTY, or FastAPI, on the grounds that they "require the claude CLI, a TTY, or a running HTTP server." Current coverage is 24%, with seven modules at ≤36%:

| Module | Cover | Why previously skipped |
|---|---|---|
| `tutor/core.py` | 10% | Uses `ClaudeSDKClient` |
| `tutor/replay.py` | 13% | Uses `ClaudeSDKClient` |
| `tutor/sink.py` | 36% | Writes stdout/stderr |
| `tutor/terminal.py` | 34% | Entry-point glue |
| `tutor/thread_pool.py` | 0% | Uses `ClaudeSDKClient` |
| `tutor/web.py` | 0% | FastAPI routes |
| `tutor/web_sink.py` | 0% | Jinja + asyncio queues |

A second look shows the assumption was too conservative. `ClaudeSDKClient` is a plain async context manager with `query()` / `receive_response()` that a ~50-line fake can satisfy; `capsys`/`monkeypatch` handle stdout/stderr; FastAPI routes are reachable via `httpx.AsyncClient(ASGITransport(app=…))` without binding a real port. `tui.py` (891 lines of Textual app surface) is the one module left out — testing it needs Textual's `Pilot` harness, which is a different project in cost and complexity.

Goal: lift project coverage from 24% → ≥85% and exercise every branch that's testable without spawning the real `claude` CLI.

## Approach

### 1. Shared fixtures — `tests/conftest.py`

Tests need four shared helpers that are painful to inline in every file:

- `FakeClaudeSDKClient` (class) — async context manager. Takes a list of pre-seeded response batches on construction. `query(text)` records the call and pops the next batch; `receive_response()` yields those messages. Built from the **real** `AssistantMessage` / `TextBlock` / `ResultMessage` classes (required: `core.py` and `thread_pool.py` use `isinstance` — `MagicMock` takes the wrong branch).
- `make_assistant(text)`, `make_result(session_id)` helpers — construct SDK messages without guessing kwargs.
- `jinja_env` fixture — returns `tutor.web.build_template_env()` so `WebSink` and web-route tests render the real partials.
- `patch_sdk_client(monkeypatch, factory)` helper — patches `tutor.replay.ClaudeSDKClient` and `tutor.thread_pool.ClaudeSDKClient` to the supplied factory.

### 2. `test_core.py` — `tutor/core.py`

- `_stdin_line_stream(use_thread=True, input_file=StringIO('a\nb\n'))` yields `'a'`, `'b'`, stops at EOF.
- `stdin_loop` happy path: one line → `sink.on_raw_line` called, `client.query` called once, `sink.on_explanation(raw, full_text)` fired with concatenated `TextBlock` text.
- Filter regex skips non-matching lines (no query, no explanation).
- Blank line and duplicate-of-last-line both skipped (lines 97 / 99).
- First `ResultMessage` triggers `save_session_id` exactly once; second ignored. Patch `tutor.core.save_session_id`.
- `client.query` raises → `sink.on_error('query failed: …')`; loop continues.
- `save_session_id` raises `OSError` → `sink.on_error('could not save session id: …')`.
- `stop_event` pre-set → loop exits without calling query.

Target: **85%**. Uncovered remainder: the non-thread branch of `_stdin_line_stream` using `loop.connect_read_pipe` (hard to drive from pytest — document as intentional gap).

### 3. `test_replay.py` — `tutor/replay.py`

- `build_preamble([])` → `''`; non-empty list round-trips each `User:`/`Assistant:` pair and ends with `(continue from here)`.
- `pairs_from_thread`: alternating roles; trailing unmatched user dropped; leading assistant dropped; empty → `[]`.
- `notify_fallback` writes `=== resume failed; replayed X/Y … ===\n` to log and calls `sink.on_error(msg)`.
- `connect_with_fallback` success: `ClaudeSDKClient(primary)` enters cleanly → returned, no fallback notice.
- `connect_with_fallback` no-resume failure: primary with `resume=None` fails → exception re-raised verbatim.
- `connect_with_fallback` resume fallback: primary with `resume='abc'` fails, fresh enters, preamble sent via `fresh.query`, `notify_fallback` fires; assert preamble contains the most-recent pair.
- Empty `tutor_entries` on fallback → no preamble query but fallback notice with `replayed=0`.

Target: **95%**.

### 4. `test_sink.py` — `tutor/sink.py`

- `ansi_enabled()`: true when stdout isatty + no `NO_COLOR`; false with `NO_COLOR=1`; false when stdout not a tty (`monkeypatch.setattr(sys.stdout, 'isatty', lambda: False)`).
- `TerminalSink.on_raw_line` writes to stdout (via `capsys`) and log (`io.StringIO`).
- `on_explanation` ansi=True: header/footer contain ANSI escapes (`\033[2m\033[36m`); ansi=False: plain `────` rule. Log contains `--- explanation for: {raw}` markers.
- `on_explanation` schedules `tutor_store.append_async`; `flush_pending_writes` awaits it. Use real `TutorStore` on `tmp_path` and assert the entry on disk.
- `on_error` writes to stderr with `[oh-language-tutor]` prefix.
- No-op methods (`on_thread_chunk`, `on_thread_done`, `on_thread_list`, `on_tutor_entry_removed`) return `None` and don't raise.

Target: **95%**.

### 5. `test_web_sink.py` — `tutor/web_sink.py`

- `subscribe()` returns a queue, `unsubscribe` removes it.
- `_broadcast` delivers `(event, payload)` to every live subscriber and strips `\n`/`\r`.
- `on_raw_line` writes only to log (no broadcast, no store write).
- `on_explanation` appends via store (flush + assert on disk) and broadcasts `explanation` with the rendered `partials/line.html`.
- `on_thread_chunk` broadcasts an OOB `<span>` with escaped thread id.
- `on_thread_done(thread, text)` → rendered markdown inside `<div>`; empty text → empty placeholder `<div>`.
- `on_thread_list` updates `latest_thread_list()` and broadcasts `partials/thread_list.html`.
- `on_tutor_entry_removed` broadcasts a delete OOB fragment.
- `on_error` renders `partials/toast.html`.
- Slow subscriber: fill queue to `_SUBSCRIBER_QUEUE_MAX`, next broadcast drops that subscriber and logs `[warn] dropping …`.

Target: **95%**.

### 6. `test_thread_pool.py` — `tutor/thread_pool.py`

Patch `tutor.thread_pool.ClaudeSDKClient` with the `FakeClaudeSDKClient` factory. Use a recording-sink class + real `ThreadStore` / `TutorStore` on `tmp_path`.

- `open_thread` with unknown anchor → `sink.on_error('tutor entry … not found')`; no active entry.
- `open_thread` success seeds `_active`, writes `=== thread open …` to log, does **not** connect a client yet.
- `reopen_thread` missing → error; present → `_active` populated with `resume_session_id`.
- `send_message` for unknown thread → error, no crash.
- `send_message` happy path: user message persisted before streaming, `on_thread_chunk` fired per `TextBlock`, assistant reply persisted in `finally`, `on_thread_done(thread, reply)` fired, thread list refreshed twice (user + assistant).
- `send_message` fresh-connect failure → `on_error` + `on_thread_done(thread, '')`.
- `send_message` resume failure: second `_connect('', None)` called, preamble sent via replay, `notify_fallback` emitted; subsequent turns use the fresh session.
- `hide_thread` cancels a stuck task after 2 s (monkeypatch `asyncio.wait_for` or shrink the timeout via a module-level constant patch).
- `delete_thread` removes the on-disk file and refreshes the thread list.
- `delete_tutor_entry` closes active anchored threads, calls `tutor_store.delete_async`, emits `on_tutor_entry_removed`. Empty `anchor_id` → no-op.
- `close_all` iterates `_active` and disconnects each.
- `list_threads` / `peek_meta` / `load_thread_meta` delegate correctly; `peek_meta` prefers in-memory meta over disk.

Target: **80%**.

### 7. `test_terminal.py` — `tutor/terminal.py`

- Invalid `--filter-regex` → `SystemExit` with `oh-language-tutor: invalid --filter-regex:` message.
- Happy path: build a fake `args` namespace with tmp paths, patch `tutor.terminal.connect_with_fallback` to return a fake client, patch `tutor.terminal.stdin_loop` to a no-op awaitable. Run `run_terminal(args)`. Assert: state dir created, log contains `=== session start …` and `=== session end ===`, return code 0, client `__aexit__` called, `sink.flush_pending_writes` awaited.
- `resume_id` present → `connect_with_fallback` receives `tutor_entries=[…]` loaded from the store; absent → empty list.
- SIGINT handler registration wrapped in `contextlib.suppress(NotImplementedError)` — monkeypatch `add_signal_handler` to raise, confirm it's swallowed.

Target: **85%**.

### 8. `test_web.py` — `tutor/web.py` (route tests via `httpx.ASGITransport`)

Build a stubbed `WebContext` fixture: tmp `tutor_store` + `thread_store`, real `WebSink` with real Jinja env, a minimal fake `FollowupThreadPool` (record calls; no real SDK), a fake entered client. Then use `httpx.AsyncClient(transport=ASGITransport(app=build_app(ctx)))`.

- `thread_heading(meta)` — unit test: first user message line wins; falls back to `anchor_raw` when no user message.
- `build_template_env()` returns `Environment` with autoescape enabled; `get_template('partials/line.html')` succeeds; globals include `render_markdown`, `format_created_at_utc`, `thread_heading`.
- `GET /` returns 200 with HTML containing the language names and any pre-existing tutor entries.
- `GET /events` yields the `: connected\n\n` comment frame immediately and the initial `event: thread_list` frame; cancel the request to exit cleanly.
- `GET /threads/{id}` 404 when `peek_meta` returns `None`; 200 renders `partials/thread_conversation.html` for a present thread; calls `reopen_thread` when thread not yet active.
- `POST /commands/open_thread` returns 200; `pool.open_thread` called with the generated `thread_id`; `on_thread_list` fired.
- `POST /commands/send_message` returns 200 with the `send_message_result.html` fragment; `pool.send_message(thread_id, text)` called.
- `POST /commands/hide_thread` returns 204; `pool.hide_thread(thread_id)` called.
- `POST /commands/delete_thread` returns 200 with the "Thread deleted." fragment.
- `POST /commands/delete_tutor_entry` returns 204; `pool.delete_tutor_entry(anchor_id)` called.
- `_uvicorn_log_config()` returns a dict with stderr stream + WARNING level for the three uvicorn loggers.

Target: **75%** (the `run_web` entry point boots uvicorn — leave it uncovered).

### 9. `pyproject.toml` / `Makefile`

No changes. `asyncio_mode = "auto"` is set; ruff per-file ignores already allow bare asserts and private access in tests; `httpx` is in the dev group. `make test` / `make lint` rules already exist.

## Critical files

- **Edit** `tests/conftest.py` — add `FakeClaudeSDKClient`, `make_assistant` / `make_result`, `jinja_env` fixture, `patch_sdk_client` helper.
- **New** `tests/test_core.py`, `tests/test_replay.py`, `tests/test_sink.py`, `tests/test_web_sink.py`, `tests/test_thread_pool.py`, `tests/test_terminal.py`, `tests/test_web.py`.
- Reuses existing: `tutor.web.build_template_env`, `tutor.tutor_store.TutorStore`, `tutor.thread_store.ThreadStore`, real `AssistantMessage`/`TextBlock`/`ResultMessage` from `claude_agent_sdk`.

## Verification

1. `make test` — ~95 new tests (total ~165) pass; no `RuntimeWarning: coroutine was never awaited`.
2. `uv run --frozen pytest --cov` per-module targets:
   - `core.py` ≥85%, `replay.py` ≥95%, `sink.py` ≥95%, `web_sink.py` ≥95%, `thread_pool.py` ≥80%, `terminal.py` ≥85%, `web.py` ≥75%.
   - Modules already at 100% stay at 100%.
   - **Project total ≥85%.**
3. `make lint` — ruff format, ruff check, basedpyright `typeCheckingMode=all`, and xenon all clean. `FakeClaudeSDKClient` may need `# noqa: BLE001` or similar on its dispatch — adjust within the existing test-file per-file-ignores rather than relaxing repo-wide rules.

## Out of scope

- `tutor/tui.py` — 891-line Textual `App`. Meaningful tests need Textual's `Pilot` harness; slow, flaky under CI load, and breaks on Textual minor bumps (pinned at `textual==8.2.3`). Coverage ROI is much lower than the business-logic modules we already cover. Deferred indefinitely.
- `tutor/web.py:run_web` and `_uvicorn_log_config`-driven server startup — we cover the helper itself but don't boot uvicorn.
- End-to-end tests that spawn the real `claude` CLI — still out of scope; the SDK surface is faked throughout.

## Final commit location

After approval, the plan file should be copied to `docs/plans/2026-04-18-17-improve-test-coverage.md` (today is 2026-04-18; last plan for today was `-16-`). The current draft lives in `~/.claude/plans/` only because plan mode is active.
