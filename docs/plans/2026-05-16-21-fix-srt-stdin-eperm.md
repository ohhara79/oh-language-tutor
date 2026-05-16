# Fix `srt.sh` stdin EPERM crash

## Context

Running `scripts/srt.sh` against an SRT file pipes `awk` output into `uv run --frozen --no-dev main.py`. The Python process starts, prints the web UI URL, then asyncio raises:

```
PermissionError: [Errno 1] Operation not permitted
  ... selector_events.py:283 in _add_reader
  ... unix_events.py:521 in _UnixReadPipeTransport._add_reader
```

EPERM from `epoll_ctl` means the kernel refused to register that file descriptor for readiness events. Under `awk | uv run main.py` on Python 3.14.2 the deferred `_add_reader` callback fires after `_UnixReadPipeTransport.__init__` accepted stdin (it passed the FIFO/socket/char-device check), but the actual `epoll_ctl(EPOLL_CTL_ADD)` is rejected. The asyncio reader-pipe path is genuinely fragile — the project's own design notes already warn about it (`docs/plans/2026-04-17-01-web-ui.md:91,150` avoid `uvicorn[standard]` specifically to dodge uvloop edge cases with `connect_read_pipe`).

The bug surfaces because `tutor/web.py:670-672` calls `stdin_loop(...)` with **default** kwargs:

```python
stdin_task = asyncio.create_task(
    stdin_loop(writing_session.sink, filter_re, stop_event),
)
```

That routes through the `else` branch of `_stdin_line_stream` (`tutor/core.py:50-59`), which calls `loop.connect_read_pipe(lambda: protocol, sys.stdin)` and crashes.

The `if use_thread:` branch (`tutor/core.py:43-49`) reads via `loop.run_in_executor(None, source.readline)` and works for regular files, pipes, sockets — everything. Every test in `tests/test_core.py` already drives the code with `use_thread=True`; the broken branch has zero test coverage (plans `2026-04-18-17` and `2026-04-18-18` explicitly call it out as "intentional gap — hard to drive from pytest").

## Approach

The two-branch `_stdin_line_stream` and the `use_thread` parameter only existed because the old TUI (`gui.py` / Textual) had to share the tty fd with the renderer — see `docs/plans/2026-04-15-02-fix-gui-input-without-pipe.md`. The TUI is gone (`b3aaf26 Rename gui to tui` followed by removal in `2205539 Make explanations on-demand`), so there's only ever one caller now (web), one transport (stdin), and the production path doesn't even use the branch the parameter selects — it uses the default `use_thread=False` branch, which is the one that crashes. Flatten the whole thing.

1. **`tutor/core.py`**: collapse `_stdin_line_stream` + `stdin_loop` into a single function and drop the dead branch / dead parameter.
   - Delete `_stdin_line_stream` entirely.
   - Rewrite `stdin_loop` to read inline via `asyncio.to_thread(source.readline)` (the modern idiom; no `run_in_executor`, no `get_running_loop`, no `StreamReader` / `connect_read_pipe`). Keep the existing `input_file: IO[str] | None = None` injection seam — tests rely on it and it's a clean boundary.
   - Drop the `use_thread` parameter.
   - Final shape:
     ```python
     async def stdin_loop(
         sink: OutputSink,
         filter_re: re.Pattern[str] | None,
         stop_event: asyncio.Event,
         *,
         input_file: IO[str] | None = None,
     ) -> None:
         source = input_file or sys.stdin
         last_kept: str | None = None
         while not stop_event.is_set():
             raw = await asyncio.to_thread(source.readline)
             if not raw:
                 return
             raw_line = raw.rstrip('\n')
             sink.on_raw_line(raw_line)
             line = raw_line
             if filter_re:
                 m = filter_re.search(raw_line)
                 if not m:
                     continue
                 if filter_re.groups and m.group(1) is not None:
                     line = m.group(1)
             if not line.strip():
                 continue
             if line == last_kept:
                 continue
             last_kept = line
             sink.on_entry_appended(TutorEntry(raw=line))
     ```
2. **`tutor/web.py`** (line 670-672): no change.
3. **`tests/test_core.py`**:
   - Drop `_stdin_line_stream` from the import line.
   - Delete the two `_stdin_line_stream` tests — their behavior (yields stripped lines, stops at EOF) is already covered transitively by `test_stdin_loop_appends_unexplained_entry` and the other `stdin_loop` tests.
   - Remove the `use_thread=True` kwarg from every remaining `stdin_loop` call.

## Files

- `tutor/core.py` — rewrite to single function (~25 lines net deletion).
- `tests/test_core.py` — drop two tests + the kwarg at 6 remaining call sites.

## Verification

1. `make lint` — basedpyright + ruff clean.
2. `uv run --frozen pytest tests/test_core.py` — all stdin tests pass.
3. Repro the original failure path:
   ```
   ./scripts/srt.sh ~/Downloads/Friends/Friends\ Season\ 1/Friends\ -\ \[1x01\]\ -\ The\ One\ where\ Monica\ gets\ a\ Roommate.srt
   ```
   Expect: no asyncio traceback. `[oh-language-tutor] web UI at http://127.0.0.1:8000` prints, the awk-cleaned subtitle lines flow into the web UI without crashing.
4. Sanity-check the `state/` already-exists path too (`scripts/srt.sh` line 7 — uses `< /dev/null`); confirm the program still starts without stdin.
