# Repo layout & build

Arvel is a `uv` workspace monorepo: one virtualenv, one lockfile, several packages. The framework core is `packages/arvel`; everything else is a companion library or the e-commerce kit.

**Source**: root `pyproject.toml` (`[tool.uv.workspace]`), `Makefile`, `CONTRIBUTING.md`.

## Layout

```
arvel/
├── packages/
│   ├── arvel/                 # framework core + CLI (PyPI: arvel)
│   │   └── src/arvel/
│   │       ├── _skeleton/      # project template for `arvel new`
│   │       ├── console/        # CLI infra + built-in commands
│   │       ├── application/    # Application, ApplicationBuilder
│   │       ├── container/      # service container
│   │       ├── providers/      # baseline service providers
│   │       ├── database/       # Arvent ORM
│   │       ├── http/           # routing, middleware, requests, resources
│   │       └── <subsystems>/   # cache, queue, events, mail, …
│   └── arvel-audit / -image / -oauth / -permission / -search
├── kits/
│   └── arvel-ecommerce-kit/    # reference app (backend + Vue frontend)
├── benchmarks/
├── docs/                       # existing site + SDLC artifacts
└── pyproject.toml              # workspace root, shared tool config
```

## Toolchain

- **Python 3.14+** and **uv 0.9+** (CI pins uv `0.11.16`).
- All shared tool config (`ruff`, `mypy`, `pyright`, `pytest`, `coverage`) lives in the **root** `pyproject.toml`, so every package is checked under one ruleset.
- `[tool.uv.sources]` pins the five libraries to the workspace; `[dependency-groups] dev` installs `arvel[all]` plus the libs and dev tooling.

## Common commands

| Command | What it does |
|---|---|
| `make sync` (`make dev`) | `uv sync --all-packages --all-extras` — install everything |
| `make lint` | `ruff format` then `ruff check --fix` |
| `make typecheck` | `mypy --strict` (+ search/audit test dirs) and `pyright --strict` |
| `make test` | fast tests — no Docker, no emulators |
| `make test-integration` | full suite; boots Testcontainers emulators |
| `make coverage` | tests + coverage (fail-under 90) |
| `make security` | `bandit` + `pip-audit` + `gitleaks` |
| `make docs` | `mkdocs build --strict` |
| `make ci` | `lint format-check typecheck coverage docs` — the local CI gate |
| `make build` | build sdist + wheel for `arvel` |

> **Note**: Run `make ci` before pushing — it mirrors the CI gate. See [quality gates](quality-gates.md) for what each check enforces and the project's zero-warnings policy.

## See also

- [Quality gates](quality-gates.md) · [Testing](testing.md) · [Conventions](conventions.md)
