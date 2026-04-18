# oh-language-tutor — agent rules

## Always

- Use `uv run --frozen <cmd>` for Python. Never bare `python`/`python3`.
- Type checker is `basedpyright`. Never write "pyright".
- Run `make lint` before declaring work done; `make format` auto-fixes.
- Python 3.14+. No backwards-compat shims.
- Plans live in `docs/plans/` named `YYYY-MM-DD-NN-slug.md` (NN always present, starts at 01).

## Topic rules (read on demand)

- Python tooling — `docs/rules/python.md`
- Writing plan files — `docs/rules/plans.md`
- Project structure & conventions — `docs/rules/project-structure.md`

## Not here

- User-facing setup — `README.md`
- Design history — `docs/plans/`
