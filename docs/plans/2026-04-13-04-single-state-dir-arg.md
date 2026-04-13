# Plan: Replace `--session-file` / `--log-file` with single `--state-dir`

## Context

Multiple state files are created under `state/` (session.id, tutor.log, threads/, tutor.json). Currently `--session-file` and `--log-file` are separate CLI args pointing into that directory. The user wants a single `--state-dir` option instead, with all file paths derived from it.

State dir layout (unchanged from today):
- `<state-dir>/session.id`
- `<state-dir>/tutor.log`
- `<state-dir>/threads/<thread_id>.json`
- `<state-dir>/tutor.json`

## Changes

### 1. `tutor/args.py` — Replace CLI args

- Remove `DEFAULT_SESSION_FILE` and `DEFAULT_LOG_FILE` constants
- Add `DEFAULT_STATE_DIR = PROJECT_DIR / 'state'`
- Remove `--session-file` and `--log-file` arguments
- Add `--state-dir` argument (default: `DEFAULT_STATE_DIR`)
- Keep all other args unchanged

### 2. `tutor/core.py::run_terminal()` (~line 191-221)

- Derive paths from `args.state_dir` instead of `args.log_file` / `args.session_file`:
  - `state_dir = Path(args.state_dir).expanduser()`
  - `state_dir.mkdir(parents=True, exist_ok=True)`
  - `log_path = state_dir / 'tutor.log'`
  - `session_path = state_dir / 'session.id'`

### 3. `tutor/gui.py::OhLanguageTutorApp.launch()` (~line 459-491)

- Same derivation as core.py:
  - `state_dir = Path(args.state_dir).expanduser()`
  - `state_dir.mkdir(parents=True, exist_ok=True)`
  - `log_path = state_dir / 'tutor.log'`
  - `session_path = state_dir / 'session.id'`
- `ThreadStore` and `TutorStore` already derive from `log_path.parent` — simplify to use `state_dir` directly

### 4. `tutor/session.py::load_saved_session_id()` (~line 12-22)

- Change to read from `Path(args.state_dir).expanduser() / 'session.id'` instead of `args.session_file`

## Files to modify

- `tutor/args.py`
- `tutor/core.py`
- `tutor/gui.py`
- `tutor/session.py`

## Verification

- `uv run --frozen oh-language-tutor --source-language English --target-language Korean --state-dir /tmp/test-state` — confirm state files created under `/tmp/test-state/`
- `uv run --frozen oh-language-tutor --help` — confirm `--state-dir` appears, `--session-file`/`--log-file` gone
- Run existing tests if any: `uv run --frozen pytest`
