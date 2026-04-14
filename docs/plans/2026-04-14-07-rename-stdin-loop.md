# Rename `_stdin_loop` → `stdin_loop`

## Context

`tutor/core.py` defines `_stdin_loop`, but the leading underscore conventionally marks a symbol as private to its defining module. In practice this function is imported and called from two other modules:

- `tutor/terminal.py:14` (top-level import) and `terminal.py:59` (call site)
- `tutor/gui.py:595` (runtime import) and `gui.py:600` (call site)

Because basedpyright treats underscore-prefixed module-level names as private, the definition at `tutor/core.py:75` carries a `# pyright: ignore[reportUnusedFunction]` comment to silence a false-positive "unused function" warning. That suppression is a smell — the real fix is to name the function according to its actual visibility.

Dropping the underscore aligns the name with how it's used and removes the need for the `pyright: ignore` comment.

## Change

Rename `_stdin_loop` → `stdin_loop` at the definition and all call sites.

## Files to modify

1. **`tutor/core.py`** (line 75)
   - Rename `async def _stdin_loop(` → `async def stdin_loop(`
   - Remove the trailing `  # pyright: ignore[reportUnusedFunction] - imported by terminal.py and (at runtime) by gui.py` comment (no longer needed once the name is public).

2. **`tutor/terminal.py`**
   - Line 14: `from tutor.core import _stdin_loop` → `from tutor.core import stdin_loop`
   - Line 59: `await _stdin_loop(...)` → `await stdin_loop(...)`

3. **`tutor/gui.py`**
   - Line 595: `from tutor.core import _stdin_loop  # noqa: PLC0415` → `from tutor.core import stdin_loop  # noqa: PLC0415`
   - Line 600: `await _stdin_loop(` → `await stdin_loop(`

## Notes

- The sibling helper `_stdin_line_stream` (core.py, called only from `_stdin_loop` inside the same module) stays underscore-prefixed — it really is private to `core.py`.
- Earlier plan files under `docs/plans/` reference `_stdin_loop` historically. Those are completed/historical plans describing prior state; leave them as-is so the historical record stays accurate.

## Verification

After the rename:

1. Type check: `uv run --frozen basedpyright` — should pass, and should no longer need the `reportUnusedFunction` suppression in `core.py`.
2. Smoke test terminal mode: pipe a line of input through the standard terminal invocation and confirm it still reaches Claude and emits output.
3. Smoke test GUI mode: launch with `--gui` and confirm stdin lines still flow into the UI.
