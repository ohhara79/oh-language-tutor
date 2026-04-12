# Plan: Followup Question Threads with Textual TUI

## Context

The user wants to add an interactive GUI feature to oh-language-tutor: the ability to click "Ask" on any explanation block, type a free-form question about that line (e.g., "Is 'cat' derogatory here?"), and have a multi-turn conversation with Claude about it in a side thread — without affecting the main session.

The current tool is a single-file terminal app (`main.py`, 324 lines) that reads stdin, sends lines to a persistent Claude session, and prints explanations to stdout. The `run()` function scores C (19) on radon — exactly at the xenon ceiling. Adding GUI + followup logic to it is impossible without a module split.

**Architecture decision:** Side conversation per followup thread (Architecture B). Each thread spins up a separate `ClaudeSDKClient` seeded with recent context from the main stream. The main session is never touched by followup questions — zero pollution, full concurrency with the live stream.

**GUI decision:** Textual TUI as the first deliverable. In-process (no IPC), pure Python, handles Korean text well, integrates naturally with asyncio.

## File layout

```
oh-language-tutor/
  main.py                    # thin entry point (~20 lines)
  tutor/
    __init__.py              # exports run_terminal, run_gui
    types.py                 # shared dataclasses, Protocol, type aliases
    prompts.py               # all system-prompt builders (base, extra, thread)
    session.py               # session id load/save (extracted from main.py)
    sink.py                  # OutputSink protocol + TerminalSink
    registry.py              # LineRegistry (in-memory line history)
    thread_store.py          # on-disk thread metadata + message persistence
    thread_pool.py           # FollowupThreadPool (side-session lifecycle)
    core.py                  # core stdin loop + command dispatcher
    args.py                  # parse_args + CLI flags
    gui.py                   # Textual App + widgets
    gui_launcher.py          # deferred import wrapper for run_gui
  state/
    threads/                 # one JSON file per thread (git-ignored)
```

Terminal-only mode (default, `--gui` not set) works exactly as today. The `textual` import only happens when `--gui` is passed.

## Implementation steps

### Step 1: Create `tutor/` package with type definitions

**New file: `tutor/types.py`** (~70 lines)

Shared dataclasses and protocols used across all modules:

- `LineRecord(idx, raw, explanation, timestamp)` — one entry in the line registry
- `OutputSink(Protocol)` — methods: `on_raw_line`, `on_explanation`, `on_thread_chunk`, `on_thread_done`, `on_thread_list`, `on_error`
- `ThreadMeta(thread_id, anchor_raw, session_id, created_at, messages)` — persisted thread state; `messages` is a list of `ThreadMessage(role, text)` (role = "user" | "assistant")
- `OpenThreadCmd`, `ReopenThreadCmd`, `SendMessageCmd`, `HideThreadCmd`, `DeleteThreadCmd` — command channel payloads
- `Cmd` — union of all command types

### Step 2: Extract existing code into modules

**New files from `main.py` extraction (no behavior change):**

- **`tutor/prompts.py`** (~90 lines) — `build_base_system_prompt`, `build_system_prompt` extracted verbatim. The prompt template uses per-line `# noqa: E501` and `# noqa: RUF001` comments where needed (the current file-level `# ruff: noqa:` in `main.py` is removed). Also add `build_thread_system_prompt` (new, for side sessions).
- **`tutor/session.py`** (~30 lines) — `load_saved_session_id`, `save_session_id` extracted verbatim.
- **`tutor/args.py`** (~90 lines) — `parse_args` extracted verbatim, plus new `--gui` flag.
- **`tutor/sink.py`** (~80 lines) — `TerminalSink` implementing `OutputSink`. Contains `ansi_enabled`, `print_header`, `print_footer`, `extract_label`, and all `sys.stdout.write` / log-write logic currently inline in `run()`.

### Step 3: Build the line registry

**New file: `tutor/registry.py`** (~50 lines)

In-memory ordered list of `LineRecord` objects so the GUI can refer to lines by index and threads can pull context.

- `add_line(raw) -> int` — returns the line index
- `set_explanation(idx, text)` — called after Claude responds
- `recent(n=20) -> list[LineRecord]` — last N lines for context injection
- `get(idx) -> LineRecord | None` — lookup by index
- Capped at 500 entries via `collections.deque` + `dict` side-index

### Step 4: Build the thread system prompt builder

**In `tutor/prompts.py`:**

`build_thread_system_prompt(source_language, target_language, level, anchor, context_lines) -> str`

Builds a side-session system prompt containing:
- Audience info (language pair, level)
- Last 10-20 dialog lines from the registry as context (oldest first)
- The anchor line marked with `>>>`, **including its full explanation if available** (translation, vocabulary, expression, context sections). This means the user can ask follow-up questions about the raw input sentence, about the explanation itself, or about anything in between — Claude sees both and understands from context
- Instruction to answer conversationally and accept follow-ups

### Step 5: Build the thread store (on-disk persistence)

**New file: `tutor/thread_store.py`** (~80 lines)

Manages per-thread JSON files in `state/threads/`. Each thread is stored as `state/threads/{thread_id}.json`:

```json
{
  "thread_id": "a1b2c3",
  "anchor_raw": "0: \"You're a pretty smart looking cat.\"",
  "session_id": "f31ecf74-...",
  "created_at": "2026-04-12T14:30:00",
  "messages": [
    {"role": "user", "text": "Is 'cat' derogatory here?"},
    {"role": "assistant", "text": "아니에요, 여기서 ..."}
  ]
}
```

API:
- `list_threads() -> list[ThreadMeta]` — reads all JSON files, returns sorted by `created_at` descending
- `load_thread(thread_id) -> ThreadMeta` — loads one thread
- `save_thread(meta: ThreadMeta) -> None` — writes/overwrites the JSON file (atomic via write-to-temp + rename)
- `delete_thread(thread_id) -> None` — removes the JSON file

The `state/threads/` directory is created on first use. Already covered by the existing `state/` entry in `.gitignore`.

### Step 6: Build the followup thread pool

**New file: `tutor/thread_pool.py`** (~130 lines)

`FollowupThreadPool` manages side `ClaudeSDKClient` sessions with persistence:

- `open_thread(thread_id, anchor_idx)` — builds context prompt via `build_thread_system_prompt`, creates a new `ClaudeSDKClient`, enters its async context manager, saves initial `ThreadMeta` to disk via `ThreadStore`
- `reopen_thread(thread_id)` — loads `ThreadMeta` from disk, creates a new `ClaudeSDKClient` with `resume=meta.session_id` (Claude remembers the full prior conversation), notifies sink with saved messages so the GUI can display conversation history, session is ready for new questions immediately
- `send_message(thread_id, text)` — calls `client.query(text)`, spawns an asyncio task that streams `receive_response()` → calls `sink.on_thread_chunk` per `TextBlock`, then `sink.on_thread_done` after completion. After the full response is buffered, appends both user message and assistant response to `ThreadMeta.messages` and saves to disk. **No SKIP buffering** — all responses are shown, streamed directly
- `hide_thread(thread_id)` — disconnects the `ClaudeSDKClient` to free resources, but keeps the `ThreadMeta` on disk. The thread can be reopened later via `reopen_thread`
- `delete_thread(thread_id)` — disconnects client if active, removes `ThreadMeta` from disk
- `close_all()` — disconnects all active clients on shutdown (metadata stays on disk for next run)
- `list_threads() -> list[ThreadMeta]` — delegates to `ThreadStore.list_threads()` for the GUI thread list

Thread conversations are also logged to `tutor.log` with markers:
```
=== thread open anchor_raw="..." thread_id={tid} ===
[user] {question}
[assistant] {full response}
=== thread close thread_id={tid} ===
```

### Step 7: Refactor the core loop

**New file: `tutor/core.py`** (~130 lines)

The current `run()` body (C=19) is split into:

- `_stdin_loop(client, sink, registry, filter_re, skip_token, stop_event, log)` — the per-line processing (passthrough → filter → dedup → query → buffer → emit to sink). Calls `sink.on_raw_line` and `sink.on_explanation` instead of writing directly. Expected complexity: B (~11).
- `_dispatch_commands(queue, pool, stop_event)` — reads from `asyncio.Queue[Cmd]`, dispatches to pool methods. Handles: `OpenThreadCmd` → `pool.open_thread`, `ReopenThreadCmd` → `pool.reopen_thread`, `SendMessageCmd` → `pool.send_message`, `HideThreadCmd` → `pool.hide_thread`, `DeleteThreadCmd` → `pool.delete_thread`. Expected complexity: B (~6).

Both run concurrently via `asyncio.TaskGroup`.

**New file: `tutor/__init__.py`** (~10 lines) — exports `run_terminal`, `run_gui`.

`run_terminal(args)` creates a `TerminalSink`, `LineRegistry`, `ThreadStore`, `FollowupThreadPool`, `asyncio.Queue[Cmd]`, and runs `_stdin_loop` + `_dispatch_commands` in a `TaskGroup`. This preserves 100% of the current terminal behavior.

### Step 8: Refactor `main.py` to thin entry point

**Modified: `main.py`** (~20 lines)

```python
from tutor.args import parse_args
from tutor import run_terminal, run_gui

def main() -> None:
    args = parse_args()
    fn = run_gui if args.gui else run_terminal
    try:
        rc = asyncio.run(fn(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)
```

### Step 9: Build the Textual GUI

**New file: `tutor/gui.py`** (~400 lines)

Layout:

```
+-----------------------------------------+----------------------+
| StreamPane (left, 60%)                  | ThreadPane (right)   |
|                                         | (hidden until open)  |
|  ScrollableContainer                    |                      |
|    LineBlock (raw line)                 |  ThreadHeader        |
|    ExplanationBlock                     |  (anchor line text)  |
|      [Ask] button                       |                      |
|    LineBlock                            |  ThreadList          |
|    ExplanationBlock                     |  (or message history)|
|      [Ask] button                       |                      |
|    ...                                  |  ScrollableContainer |
|                                         |    user message      |
|                                         |    assistant message |
|                                         |    ...               |
|                                         |                      |
+-----------------------------------------+  Input + Send btn   |
| StatusBar                               |                      |
+-----------------------------------------+----------------------+
```

- `TutorApp(App)` implements `OutputSink` — receives events from the core loop and updates widgets via `call_from_thread`
- `LineBlock(Static)` — raw line, carries `line_idx`, has an `[Ask]` button
- `ExplanationBlock(Static)` — rendered explanation text
- `ThreadPane` — right panel, two modes:
  1. **Thread list mode** (default when no thread is active): shows a list of all saved threads from `state/threads/`, each displaying the truncated anchor line and timestamp. Click to reopen.
  2. **Conversation mode** (after opening/reopening a thread): shows thread header + scrollable message history + text input for follow-ups
- `ThreadListItem(ListItem)` — one row per saved thread: truncated anchor line + created-at date + [Delete] button
- Streaming: `on_thread_chunk` appends text incrementally to the thread log widget

**Thread interaction flow:**
1. On app start, `ThreadPane` loads the thread list from disk via `pool.list_threads()` and shows it
2. User clicks `[Ask]` on a line → new thread created (`OpenThreadCmd`), conversation mode shown, input focused
3. User types question, presses Enter → user message displayed, `SendMessageCmd` posted
4. Pool streams response → `on_thread_chunk` appends to thread log in real-time, message saved to disk on completion
5. User asks follow-up → repeat from step 3
6. User presses Escape → thread hidden (`HideThreadCmd`), session disconnected, metadata stays on disk, thread list shown again
7. User clicks a thread in the thread list → thread reopened (`ReopenThreadCmd`), session resumed with `resume=session_id`, saved messages displayed, conversation mode shown, user can ask new follow-ups
8. User clicks [Delete] on a thread → `DeleteThreadCmd` posted, JSON file removed, thread list updated

**One active thread at a time.** Opening/reopening a different thread hides the current one first.

**New file: `tutor/gui_launcher.py`** (~20 lines) — deferred `import textual` + wiring. Called only when `--gui` is set.

### Step 10: Update dependencies and config

**Modified: `pyproject.toml`**

- Add `"textual>=0.86"` to `[project.dependencies]`
- Use per-line `# noqa:` comments where needed (e.g., long prompt template lines). Do NOT use per-file-ignores in `pyproject.toml` or file-level `# ruff: noqa:` directives

### Step 11: Lint pass and verification

Run `make lint` — all four checks (ruff format, ruff check, basedpyright, xenon) must pass.

## Complexity budget

| Module | Worst function | Expected score |
|---|---|---|
| `main.py` | `main` | A (2) |
| `tutor/core.py` | `_stdin_loop` | B (11) |
| `tutor/thread_pool.py` | `_stream_thread_response` | B (7) |
| `tutor/thread_store.py` | `save_thread` | A (3) |
| `tutor/gui.py` | `on_button_pressed` | B (8) |
| All other modules | — | A |

All well under the xenon ceiling (max-absolute C, max-modules B, max-average A).

## Edge cases addressed

- **Thread opened before explanation arrives:** context builder omits explanation if None; still works
- **stdin EOF in GUI mode:** stream pane stops updating, but open threads remain interactive; user quits explicitly
- **SIGINT in GUI mode:** Textual handles Ctrl+C → triggers cleanup of threads and background tasks
- **One active thread at a time:** opening/reopening a different thread hides the current one first
- **Reopening a thread after app restart:** `reopen_thread` loads `ThreadMeta` from disk, creates a new `ClaudeSDKClient` with `resume=session_id` so Claude remembers the full prior conversation, saved messages are displayed in the GUI before the input field appears
- **Stale thread (session expired):** if `resume=session_id` fails (session no longer exists on the server), catch the error, display a message in the thread pane ("Session expired — thread is read-only"), and show saved messages as history without enabling new input
- **Corrupt/missing thread JSON:** `load_thread` catches JSON decode errors and file-not-found, removes the entry from the thread list, logs a warning
- **Concurrent thread save:** each thread has its own JSON file, so no locking contention; atomic write via temp file + rename prevents partial writes

## Verification

1. **Terminal mode regression:** run `scripts/bladerunner.sh` without `--gui` — behavior must be identical to current
2. **Lint:** `make lint` passes (ruff format, ruff check, basedpyright, xenon)
3. **GUI smoke test:** run with `--gui`, verify:
   - Raw lines and explanations appear in the left pane as the game plays
   - Click [Ask] on an explanation → thread pane opens on the right
   - Type a question → Claude responds with streaming text
   - Ask a follow-up → Claude responds with context from the thread
   - Press Escape → thread hidden, thread list shown
4. **Context quality:** open a thread on a line mid-scene, ask "who is speaking?" — verify Claude correctly identifies the speaker from the injected context
5. **Concurrency:** open a thread and type a question while the game is advancing — verify new live lines still appear in the stream pane without blocking
6. **Log check:** verify `state/tutor.log` contains both live explanations and thread conversations with proper markers
7. **Across-run persistence:** open a thread, ask 2 questions, quit the app. Restart with `--gui` — verify the thread appears in the thread list with correct anchor line. Click it → saved messages appear, type a new follow-up question → Claude responds with full memory of the prior conversation
8. **Thread deletion:** click [Delete] on a thread in the list → verify the JSON file is removed from `state/threads/` and the thread disappears from the list
