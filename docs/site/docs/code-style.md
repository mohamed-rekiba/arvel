# Code Style

Arvel projects use **ruff** for both linting and formatting. The `arvel new` starter ships a working `pyproject.toml` configuration out of the box.

## Running

```bash
uv run ruff check .         # lint
uv run ruff format .        # format
uv run ruff check --fix .   # lint and auto-fix
```

Or via Make:

```bash
make lint
make format
```

## Configuration

Ruff is configured in `pyproject.toml`. The starter template enables a strict but practical rule set:

```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "S", "ANN"]
ignore = ["ANN101", "ANN102"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]   # allow assert in tests
```

## Pre-commit hook

The starter `.pre-commit-config.yaml` runs `ruff check` and `ruff format --check` on every commit so style problems never reach CI.

```bash
uv run pre-commit install
```

## See also

- [Contributions](contributions.md) — how to run the full quality gate locally.
- [Testing](testing.md) — running tests alongside linting.
