# arvel

**A Laravel-grade web framework for Python** — async-first, type-safe, and modular. A faithful port of Laravel's developer experience onto a modern, best-in-class Python stack.

```bash
uv add arvel                      # light core, no heavy deps
uv add 'arvel[standard]'          # the common set (http, db, queue, cache, view, mail, image)
```

## Why arvel
- **Batteries included, async-first** — routing, ORM, queue, cache, auth, mail, views, CLI — one coherent DX.
- **Type-safe** — strict typing across the public API; your editor and CI catch mistakes early.
- **Lightweight & modular** — one package, opt-in extras, lazy imports. You pay only for what you use.

## The four gates (enforced in CI from the first commit)
- **G1 — boundaries:** import-linter keeps modules honest (kernel isolation, layered DAG, no heavy import at module load).
- **G2 — startup:** `import arvel` pulls **zero** heavy libraries; the CLI stays fast.
- **G3 — types:** strict mypy + pyright on every public API.
- **G4 — stack fidelity:** each capability is built on its mandated engine (Litestar, SQLAlchemy Core, whenever, Typer, …) — verified by a per-module test.

## Develop
```bash
uv venv && uv pip install -e '.[dev]'
./tools/validate.sh               # ruff · mypy · pyright · import-linter · bandit · pip-audit · pytest
```

Built on: Litestar · SQLAlchemy Core · Alembic · whenever · Typer · taskiq · Babel · msgspec · cashews · fsspec · Jinja2. Stack rationale: see the project's decision records.
