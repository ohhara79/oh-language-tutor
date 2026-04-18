# Rename "gui" to "tui" in source code

## Context

The codebase calls the Textual-based interface a "GUI" throughout (file `tutor/gui.py`, `--gui` CLI flag, `run_gui()` entry point, various comments). This is a misnomer — Textual renders a terminal UI, not a graphical UI. The code even contradicts itself: `tutor/gui.py`'s module docstring is `"""Textual TUI for oh-language-tutor."""` and `run_gui`'s docstring says "Launch the Textual TUI." Rename everywhere so the naming matches reality.

Scope (confirmed with user): source code, README, and the bladerunner script. Historical plan docs in `docs/plans/` are left untouched as snapshots of past work. Git branches named `gui` are not renamed.

## Changes

### 1. Rename the module file

- `git mv tutor/gui.py tutor/tui.py`

### 2. `main.py`

- `if args.gui:` → `if args.tui:`
- `from tutor.gui import run_gui` → `from tutor.tui import run_tui`
- `'--gui requires textual...'` → `'--tui requires textual...'`
- `runner = run_gui` → `runner = run_tui`

### 3. `tutor/args.py`

- `'--gui',` → `'--tui',`
- `if args.gui and args.web:` → `if args.tui and args.web:`
- `'--gui and --web are mutually exclusive'` → `'--tui and --web are mutually exclusive'`
- Help string already says "Textual TUI" — no change.

### 4. `tutor/tui.py` (after rename)

- Comment: `scummvm | tutor --gui` → `scummvm | tutor --tui`
- Banner comment: `# GUI command dispatcher` → `# TUI command dispatcher`
- Docstring: `"""Read commands from the GUI ..."""` → `"""Read commands from the TUI ..."""`
- Banner comment: `# GUI entry point` → `# TUI entry point`
- `async def run_gui(...)` → `async def run_tui(...)`

### 5. `tutor/terminal.py`

- Docstring: `(default, no ``--gui``)` → `(default, no ``--tui``)`

### 6. `tutor/replay.py`

- Docstring: `` `terminal.py` / `gui.py` `` → `` `terminal.py` / `tui.py` ``

### 7. `tutor/core.py`

- Module docstring: `used by both terminal and GUI modes` → `used by both terminal and TUI modes`
- Function docstring: `Used in GUI mode where` → `Used in TUI mode where`

### 8. `tutor/thread_pool.py`

- Docstring: `so the GUI can render` → `so the TUI can render`

### 9. `tutor/types.py`

- Banner comment: `# Command channel payloads (GUI -> core loop)` → `# Command channel payloads (TUI -> core loop)`

### 10. `README.md`

- `--gui \` → `--tui \`

### 11. `scripts/bladerunner.sh`

- `--gui \` → `--tui \`
- `scripts/bladerunner.sh.org` is an untracked backup copy; leave it alone.

## Files NOT changed

- `docs/plans/**` — historical snapshots; keep "gui" as it was at the time.
- `scripts/bladerunner.sh.org` — untracked local backup.
- `.git/refs/heads/gui`, `.git/refs/remotes/origin/gui` — branch names not in scope.
- `tutor/__pycache__/gui.cpython-314.pyc` — regenerates automatically.

## Verification

1. `rg -i '\bgui\b' main.py tutor/ scripts/bladerunner.sh README.md` — should return zero hits.
2. `uv run --frozen basedpyright` — type check passes.
3. Smoke-test the renamed flag end-to-end:
   ```
   echo 'Hello world.' | uv run --frozen main.py \
     --source-language English --target-language Korean --level intermediate --tui
   ```
   Textual UI should launch (same as `--gui` did before).
4. `bash scripts/bladerunner.sh` still works (only if user wants to exercise it).
