# Plan: Persist `tutor.json` in no-TUI (terminal) mode

## Context

`state/tutor.json` is the append-only log of explained lines that rehydrates the left pane on restart. It is written correctly in TUI (`--tui`) and web (`--web`) modes but is never written when the app runs in default terminal mode, so resuming a terminal session cannot restore prior explanations and the web/TUI tools cannot see terminal-mode history.

## Root cause

The `tutor.json` write call is **UI-dependent**, not shared:

- `tutor/tui.py:424-434` — `OhLanguageTutorApp.on_explanation()` does `asyncio.create_task(self._tutor_store.append_async(entry))`.
- `tutor/web_sink.py:68-72` — `WebSink.on_explanation()` does the same.
- `tutor/sink.py:40-47` — `TerminalSink.on_explanation()` only writes to stdout and the log file; it never touches `TutorStore`.

`tutor/terminal.py:65` constructs a `TutorStore` but only uses `.load()` at line 70 to feed replay entries into `connect_with_fallback`. No write path exists.

The shared driver `tutor.core.stdin_loop` (see `tutor/core.py:122`) invokes `sink.on_explanation(raw_line, response)` and relies on each sink implementation to persist.

## Approach

Mirror what `WebSink` does: inject a `TutorStore` into `TerminalSink` and call `append_async` from `on_explanation`. Track the tasks so we can await them on shutdown, matching the TUI/web drain behavior.

## Changes

### `tutor/sink.py` — `TerminalSink`

1. Accept `tutor_store: TutorStore` in `__init__`. Store it on `self._tutor_store`.
2. Initialize `self._pending_writes: set[asyncio.Task[None]] = set()`.
3. In `on_explanation`, after the existing stdout/log writes, build a `TutorEntry(raw=raw, explanation=text)` and schedule `asyncio.create_task(self._tutor_store.append_async(entry))`. Add to `_pending_writes` and use `task.add_done_callback(self._pending_writes.discard)` — same pattern as `tutor/web_sink.py:68-72`.
4. Add `async def flush_pending_writes(self) -> None` that awaits outstanding tasks (copy the body of `WebSink.flush_pending_writes` at `tutor/web_sink.py:54-57`).

Import `TutorEntry` from `tutor.types` and `TutorStore` under `TYPE_CHECKING`.

### `tutor/terminal.py`

1. Pass `tutor_store` into `TerminalSink(log, ansi=…, tutor_store=tutor_store)` at line 64 (swap the existing construction order so `tutor_store` is built first, then `sink`).
2. After `stdin_loop` returns — inside the `finally` next to `client.__aexit__` at line 77 — call `await sink.flush_pending_writes()` so Ctrl-C / EOF doesn't lose the last explanation's write.

No change needed in `tutor/core.py` or `TutorStore` itself — `append_async` is already safe for concurrent callers via its internal `asyncio.Lock`.

## Critical files

- `tutor/sink.py` — add write path + drain
- `tutor/terminal.py` — wire `TutorStore` into sink, flush on exit
- `tutor/tutor_store.py` — reference only (`append_async` at line 64)
- `tutor/web_sink.py` — reference pattern (lines 30-72)
- `tutor/tui.py` — reference pattern (lines 388-434)

## Verification

1. Run terminal mode against a fresh state dir:
   ```
   rm -rf /tmp/tutor-test && \
   printf 'Hello world\nBonjour le monde\n' | \
     uv run --frozen oh-language-tutor --state-dir /tmp/tutor-test
   ```
   Confirm `/tmp/tutor-test/tutor.json` exists and contains two entries with `id`, `raw`, `explanation`.
2. Re-run the same command and confirm the new entries are appended (not overwritten) and prior entries are preserved.
3. Switch to `--tui` pointing at `/tmp/tutor-test`; the left pane rehydrates with all terminal-mode entries — proves the on-disk format matches.
4. Kill the terminal run mid-stream with Ctrl-C right after an explanation prints; confirm that explanation still appears in `tutor.json` (validates `flush_pending_writes` on shutdown).
5. Type-check: `uv run --frozen basedpyright tutor/sink.py tutor/terminal.py`.
