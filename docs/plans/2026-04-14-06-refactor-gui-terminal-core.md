# Refactor: split GUI/terminal code out of core.py; merge gui_launcher into gui

## Context

`tutor/core.py` currently mixes three concerns: shared stdin processing, a GUI-only command dispatcher, and the terminal-mode entry point. `tutor/gui_launcher.py` is a 21-line wrapper whose only job is to defer the `textual` import so a missing dependency produces a friendly error. The asymmetry is confusing — there is no `terminal.py`, "core" contains the terminal entry point, and a 21-line file exists for one try/except.

This refactor reshapes the layout so each module owns its mode:

- `core.py` → only the **shared** stdin pipeline (`_stdin_line_stream`, `_stdin_loop`)
- `terminal.py` → terminal mode (`run_terminal`)
- `gui.py` → GUI mode + GUI-only `_dispatch_commands` + the `run_gui` entry point
- `gui_launcher.py` → deleted; the missing-`textual` try/except moves to `main.py`

No behavior changes; this is purely a code-layout refactor.

## Changes

### 1. Create `tutor/terminal.py`

Move from `tutor/core.py`:

- `run_terminal()` (core.py:174–214)

The function imports it currently uses (`asyncio`, `contextlib`, `re`, `signal`, `Path`, `ClaudeAgentOptions`, `ClaudeSDKClient`, `build_system_prompt`, `load_saved_session_id`, `TerminalSink`, `ansi_enabled`, `argparse`) move with it. Add an import of `_stdin_loop` from `tutor.core`.

### 2. Move `_dispatch_commands` from `core.py` into `gui.py`

`_dispatch_commands()` (core.py:145–166) is only used by `gui.py:612`. Move it into `gui.py` as a module-level function (or a private helper near `OhLanguageTutorApp.launch`). Update gui.py:595's runtime import — it currently imports both `_stdin_loop` and `_dispatch_commands` from `tutor.core`; after the move, only `_stdin_loop` is imported from `tutor.core`.

The `Cmd`, `OpenThreadCmd`, `ReopenThreadCmd`, `SendMessageCmd`, `HideThreadCmd`, `DeleteThreadCmd`, `FollowupThreadPool` imports needed by `_dispatch_commands` move with it (gui.py likely already imports most of these).

### 3. `core.py` keeps only shared stdin pipeline

After the moves, `core.py` contains:

- `_stdin_line_stream()` (helper)
- `_stdin_loop()` (shared by terminal.py and gui.py)

Drop now-unused imports (`Cmd`, `OpenThreadCmd`, `ReopenThreadCmd`, `SendMessageCmd`, `HideThreadCmd`, `DeleteThreadCmd`, `TerminalSink`, `ansi_enabled`, `build_system_prompt`, `load_saved_session_id`, `signal`, `contextlib`, `re`, `argparse`, `Path`).

### 4. Merge `gui_launcher.py` into `gui.py`

Delete `tutor/gui_launcher.py`. Add a module-level `async def run_gui(args)` to `gui.py` that simply calls `OhLanguageTutorApp.launch(args)` (no try/except — that moves to main.py).

### 5. Update `main.py`

Replace the current GUI dispatch:

```python
if args.gui:
    from tutor.gui_launcher import run_gui  # noqa: PLC0415
    runner = run_gui
```

with the deferred import + try/except formerly in `gui_launcher.py`:

```python
if args.gui:
    try:
        from tutor.gui import run_gui  # noqa: PLC0415
    except ImportError:
        sys.stderr.write('[oh-language-tutor] --gui requires textual. Install it with: uv add textual\n')
        sys.exit(1)
    runner = run_gui
```

### 6. Update `tutor/__init__.py`

Change `from tutor.core import run_terminal` → `from tutor.terminal import run_terminal`. The public `__all__ = ['run_terminal']` is unchanged.

## Critical files

- `tutor/core.py` — gut down to shared pipeline
- `tutor/terminal.py` — **new**, holds `run_terminal`
- `tutor/gui.py` — gains `_dispatch_commands` and module-level `run_gui`; drops the runtime import of `_dispatch_commands` from core
- `tutor/gui_launcher.py` — **delete**
- `tutor/__init__.py` — re-export path update
- `main.py` — try/except for `textual` import moves here

## Verification

1. `uv run --frozen ruff check` and `uv run --frozen basedpyright` — must be clean.
2. Terminal mode: `echo 'hola' | uv run --frozen oh-language-tutor` (or the equivalent piped invocation) still produces an explanation.
3. GUI mode (with textual installed): `uv run --frozen oh-language-tutor --gui < some_input` still launches the Textual app, threads still open/reopen/send/hide/delete (exercises `_dispatch_commands` in its new home).
4. GUI mode without textual: temporarily uninstall `textual` and confirm `--gui` still emits the friendly `'[oh-language-tutor] --gui requires textual…'` message and exits 1.
5. Run the existing test suite if present (`uv run --frozen pytest`).
