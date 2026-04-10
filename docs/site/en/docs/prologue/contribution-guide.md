# Contribution Guide

Thank you for helping improve Arvel. Whether you are fixing a typo, adding a test, or sketching a new feature, the goal is the same: keep the framework approachable for Laravel-minded Python developers without giving up type safety or async correctness. This page covers how to set up your machine, run the test suite, and align your pull request with project standards.

## Development setup

You will need **Python 3.14+** and [**uv**](https://github.com/astral-sh/uv) for dependency management (the same workflow CI uses).

```bash
git clone https://github.com/mohamed-rekiba/arvel.git
cd arvel
uv sync --all-extras
```

`uv sync --all-extras` installs the package, development tools (pytest, ruff, ty, coverage, and friends), and optional integrations so local runs match CI as closely as possible. If you only need a subset, you can sync with specific extras — but before opening a PR, run the full suite at least once.

Quick sanity check that the environment sees the package you expect:

```python
from importlib import metadata

print(metadata.version("arvel"))
```

## Running tests

The project uses **pytest**. From the repository root:

```bash
uv run pytest tests/ -v
```

CI splits “fast” unit tests from database- and service-heavy integration tests; locally you can mirror that with markers (see `pyproject.toml` and CI workflows) when you want a quicker loop:

```bash
uv run pytest tests/ -m "not db and not integration" --timeout=10
```

For coverage in line with the project’s standards:

```bash
uv run pytest tests/ --cov=src/arvel --cov-report=term-missing
```

Fix any failures and warnings you introduce before requesting review.

## Pull requests

- **One logical change per PR** when possible — easier to review and bisect.
- **Describe what and why** in the PR body; link related issues or discussions.
- **Include tests** for behavior changes or regressions; documentation-only PRs are welcome but should still be accurate and build-clean.
- **Keep commits readable**; follow [Conventional Commits](https://www.conventionalcommits.org/) style if you can (`feat:`, `fix:`, `docs:`, etc.).

## Coding standards and type safety

Contributions should respect the repository’s tooling:

- **Ruff** for lint and format (`uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`).
- **ty** for static typing on the codebase (`uv run ty check src/ tests/`).
- **Project rules** in `.cursor/rules/` (for example type-safety, ORM, and testing expectations) — treat them as the bar for public APIs and tests.

When in doubt, match patterns in existing modules and tests: explicit types at boundaries, real SQLite-backed tests for data code, and no silent failures.

## Documentation

User-facing docs live under `docs/`; site content for MkDocs-style builds may live under `docs/site/`. If you change behavior, update the relevant page in the same PR so readers are not left behind.

Together we keep Arvel predictable, well-tested, and pleasant to work on — thanks again for contributing.
