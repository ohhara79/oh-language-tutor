# Fix `ScreenStackError` on resume-fallback path

## Context

Running `./scripts/bladerunner.sh` crashes when the Claude SDK can't resume
the prior session and the replay fallback fires. The traceback:

```
tutor/replay.py:115  notify_fallback(log, sink, ...)
tutor/replay.py:72   sink.on_error(msg)
tutor/gui.py:395     self.query_one('#status-bar', Label).update(...)
textual ... ScreenStackError: No screens on stack
```

Root cause: in `OhLanguageTutorApp.launch` (`tutor/gui.py:617`),
`connect_with_fallback(...)` runs **before** `await app.run_async()`
(line 645). When `notify_fallback` calls `sink.on_error(msg)` on the
`OhLanguageTutorApp` instance, the Textual app hasn't started yet — no
screens have been pushed — so `query_one('#status-bar', ...)` explodes.

The fallback only happens when (a) a resume id exists and (b) the SDK
rejects the resume, so it's easy to miss in normal runs.

## Recommended fix

Make `OhLanguageTutorApp.on_error` safe to call before the app is
mounted by buffering pre-mount errors and flushing them in `on_mount`.

This is a minimal, localized change — `connect_with_fallback` /
`notify_fallback` keep their current shape, and every existing caller
of `sink.on_error` continues to work.

### Changes to `tutor/gui.py`

1. In `OhLanguageTutorApp.__init__` (around line 297, next to the
   other `self._…` state), add a pre-mount error buffer:

   ```python
   self._pending_errors: list[str] = []
   ```

2. Replace `on_error` (currently `tutor/gui.py:394-395`):

   ```python
   def on_error(self, msg: str) -> None:
       if not self._screen_stack:
           self._pending_errors.append(msg)
           return
       self.query_one('#status-bar', Label).update(f'Error: {msg}')
   ```

   `self._screen_stack` (property at `textual/app.py:1199`) is the
   mounted-screen list; it's empty until `run_async()` mounts the
   default screen. Using it avoids a try/except around
   `ScreenStackError` and matches what `default_screen` itself checks.

3. In `on_mount` (`tutor/gui.py:314`), after the existing setup, drain
   the buffer so the last queued error wins (same semantics as
   overwriting `#status-bar`):

   ```python
   if self._pending_errors:
       last = self._pending_errors[-1]
       self._pending_errors.clear()
       self.query_one('#status-bar', Label).update(f'Error: {last}')
   ```

   We only surface the most recent one because `#status-bar` is a
   single `Label` that would otherwise be overwritten line-by-line;
   earlier errors are already written to the session log by
   `notify_fallback` / other callers, so no information is lost.

### Files touched

- `tutor/gui.py` — only file modified.

### Files read / not modified

- `tutor/replay.py` (`notify_fallback`, `connect_with_fallback`) —
  behaviour unchanged; it still calls `sink.on_error`.
- `tutor/types.py` — `OutputSink` protocol unchanged.
- `tutor/thread_pool.py`, `tutor/core.py`, `tutor/sink.py` — other
  `on_error` callers; all run after the app is mounted, so the new
  buffering path is a no-op for them.

## Verification

1. Type-check:

   ```
   uv run --frozen basedpyright tutor/gui.py
   ```

2. Reproduce the original failure path. The easiest trigger is to
   point the resume id at a session the SDK will reject:

   - Run `./scripts/bladerunner.sh` once to create a session, note the
     thread/session id it stored under the state dir.
   - Corrupt / rename that session on disk (or edit the saved resume
     id to a non-existent UUID) so the next launch attempts resume
     against an id the SDK doesn't know.
   - Run `./scripts/bladerunner.sh` again. Expected: the app starts
     normally, the status bar shows
     `Error: resume failed; replayed N/M turns into a new session`,
     and the session log contains the same `=== resume failed ... ===`
     line written by `notify_fallback`.

3. Sanity-check the happy path: run `./scripts/bladerunner.sh` with a
   valid (or absent) resume id and confirm the app still launches and
   the status bar shows `Listening...`.
