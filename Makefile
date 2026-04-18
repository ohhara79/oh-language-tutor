.PHONY: run lint format test

lint:
	uv run --frozen ruff format --check --diff .
	uv run --frozen ruff check .
	uv run --frozen basedpyright .
	uv run --frozen xenon --max-absolute D --max-modules C --max-average B .

format:
	uv run --frozen ruff format .
	uv run --frozen ruff check --fix .

test:
	uv run --frozen pytest --cov
