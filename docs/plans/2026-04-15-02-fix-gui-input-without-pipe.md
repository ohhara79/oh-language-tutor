# Fix GUI input responsiveness when run without a piped source

## Context

`oh-language-tutor --gui` is normally launched with scummvm piping dialog on stdin (see `scripts/bladerunner.sh`). When the user runs it **without** a pipe — i.e. stdin is the real tty — keyboard and mouse input to the Textual GUI become highly unreliable (e.g. 4 out of 5 Up-arrow presses are dropped).

### Root cause

In `tutor/gui.py:604-609`, the pipe→`/dev/tty` redirection only runs when `sys.stdin.isatty()` is False:

```python
pipe_file = None
if not sys.stdin.isatty():
    pipe_fd = os.dup(sys.stdin.fileno())
    pipe_file = os.fdopen(pipe_fd, ...)
    tty = open('/dev/tty', ...)
    os.dup2(tty.fileno(), sys.stdin.fileno())
```

When stdin is already a tty (no scummvm), the branch is skipped and `pipe_file` stays `None`. The GUI still starts the `stdin_loop` task (`gui.py:651-660`) with `use_thread=True, input_file=None`. In `tutor/core.py:50-57` this resolves `source = sys.stdin` and runs `await loop.run_in_executor(None, source.readline)` — a blocking `readline()` on the very same tty fd that Textual is reading for key/mouse events. The two readers race for each byte: whichever wakes up first consumes it, so most key/mouse events never reach Textual.

With scummvm, there is no race because `stdin_loop` reads the saved pipe fd and Textual owns the tty exclusively.

### Desired outcome

When no source stream is piped, the GUI should behave as a normal interactive Textual app (browse threads, ask follow-ups) with fully responsive keyboard and mouse. Nothing should be reading from the tty except Textual.

## Approach

Skip the `stdin_loop` task entirely when stdin is a tty. There is no dialog stream to transcribe in that case; running the loop offers zero value and actively breaks input.

### Changes

**`tutor/gui.py`** — around lines 598-680:

1. Track whether a piped source exists: `has_pipe = not sys.stdin.isatty()`. Keep the existing pipe-save / tty-redirect block (only runs when `has_pipe`).
2. Only create the `stdin_task` when `has_pipe` is True. When False:
   - Do not call `stdin_loop`.
   - Still create `dispatch_task` (needed for follow-up thread commands from the GUI).
   - App quits as today; `stop_event` is set on exit.
3. Make the task cancel/gather logic tolerate `stdin_task` being absent (build the awaited-task list conditionally).

No changes needed in `tutor/core.py`, `tutor/terminal.py`, or elsewhere — this is localized to the GUI entrypoint.

### Critical files

- `tutor/gui.py` (lines ~598-680) — only file modified
- `tutor/core.py:31-67` — reference only, to confirm the blocking-readline path

## Verification

1. **Standalone GUI (the bug):**
   `uv run --frozen main.py --gui --state-dir state/bladerunner`
   Press Up/Down/Enter repeatedly and click sidebar items. Every event should register; no drops.
2. **Piped GUI (regression check):**
   `scripts/bladerunner.sh` (scummvm piped in). Dialog lines should still flow into the left pane, and GUI key/mouse should still work.
3. **Terminal mode (regression check):**
   `echo -e "line1\nline2" | uv run --frozen main.py` — still transcribes both lines.
4. **Lint/type:** `uv run --frozen basedpyright tutor/gui.py` and project lint should pass.

## Out of scope

- Changing how `stdin_loop` itself reads (no `core.py` changes).
- Adding a CLI flag to force/disable stdin reading — the tty check is a reliable enough signal.
- Terminal (non-GUI) mode behavior when run without a pipe — unchanged.
