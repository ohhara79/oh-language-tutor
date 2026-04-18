# Python tooling

## Package manager

- `uv` is the only package manager. Never use `pip`, `poetry`, or `pipx`.
- `uv.lock` is authoritative. Do not edit it by hand; use `uv add` / `uv remove` / `uv sync`.

## Running Python

- Always use `uv run --frozen <cmd>`.
  - `--frozen` prevents silent lockfile mutation during a run.
  - Bare `python`/`python3` bypasses the managed env and is wrong.
- Example: `uv run --frozen main.py --source-language ko --target-language en`.

## Type checking

- Checker is `basedpyright` (not `pyright`). Do not write "pyright" in commands, configs, or comments.
- Config lives under `[tool.basedpyright]` in `pyproject.toml`. Mode is `all`, with selective ignores (`reportAny`, `reportPrivateUsage`, `reportUnreachable`).
- Targets Python 3.14. No `from __future__ import annotations` or other backport shims.

## Lint / format

- `ruff` for both. Config under `[tool.ruff]` in `pyproject.toml`.
  - `line-length = 120`, single quotes, broad ruleset.
- Use `make format` to auto-fix and `make lint` to verify. Avoid calling `ruff`/`basedpyright` directly so the Makefile stays the single entry point.

## Complexity

- `xenon` enforces thresholds: max-absolute `D`, max-modules `C`, max-average `B`.
- If `make lint` fails on complexity, refactor rather than suppressing.

## Before declaring work done

Run `make lint`. This runs ruff format check, ruff check, basedpyright, and xenon in sequence. All must pass.
