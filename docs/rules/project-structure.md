# Project structure & conventions

## Layout

- `main.py` — CLI entry. Parses args and dispatches to a terminal, TUI, or web runner via `asyncio.run`.
- `tutor/` — core package. Subsystems split by mode (terminal, TUI, web) plus shared prompt/session/threading logic.
- `extras/` — domain-specific prompt overlays as markdown files. These are loaded on top of the base prompt via `--extra-system-prompt`.
- `scripts/` — helper shell scripts (e.g. `bladerunner.sh`).
- `state/` — runtime session state (session IDs, logs). Gitignored.
- `docs/examples/` — sample extras files and screenshots.
- `docs/plans/` — design plans (see `docs/rules/plans.md`).
- `docs/rules/` — agent-facing topic rules (this directory).

## Conventions

- **Async throughout.** Runners are coroutines driven by `asyncio.run`. Do not introduce sync entry points.
- **Lazy imports for optional modes.** TUI (`textual`) and web (`fastapi`, `jinja2`) dependencies are imported inside their runners so terminal mode has no hard dependency on them. Preserve this when adding optional features.
- **Extras stay out of source.** Domain-specific prompt content belongs in `extras/*.md`, not embedded in Python. See `README.md` for the rule rationale.
- **External binary dependency:** the `claude` CLI must be on `$PATH`. The Agent SDK shells out to it.

## Testing

No test directory or framework is currently configured. If you need to add tests, propose the framework choice (pytest is the natural default) before creating a test harness.
