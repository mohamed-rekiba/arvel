# ADR-001 — Adopt FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq as the framework stack

**Status**: Accepted
**Date**: 2026-05-17
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous), ratified by user "ACT"
**Scope**: Whole framework

---

## Context

Arvel is a Laravel-style web framework for Python. The first architectural choice — and the one that constrains every other decision — is what underlying libraries to integrate with versus replace. Existing Python frameworks vary: Django and Masonite rebuilt their own ORM/router/container; Uvicore kept FastAPI but rebuilt the ORM on SQLAlchemy Core; the lighter FastAPI scaffolders layered conventions without replacing core libs.

We commit one way before writing framework code.

## Options considered

### Option A — Build our own ORM/router/validation (Masonite path)

**Pros**: total control, Laravel-faithful naming. **Cons**: decades of work to reach SQLAlchemy/FastAPI/Pydantic parity; we'd be the sole maintainer of a major ORM in 2026; non-standard, untyped, community distrust.

### Option B — Integrate the standard async stack (chosen)

**Pros**: ride the strongest async-Python ecosystem; inherit type-safety from Pydantic and SQLAlchemy (`Mapped[T]`, `BaseModel`); free OpenAPI from FastAPI; free async DB + migrations from SQLAlchemy + Alembic; free async queue from Taskiq; contributors already know these libraries. **Cons**: tied to the major-version cadence of several libraries (SemVer discipline mitigates); some Laravel UX needs wrappers (`where("name","x")` → `where(Model.name == "x")`).

### Option C — Adopt Litestar instead of FastAPI

**Pros**: built-in DI, higher synthetic throughput. **Cons**: smaller ecosystem, less OpenAPI tooling, and an audience mismatch — Arvel's audience overlaps heavily with FastAPI's.

## Decision

**Option B.** Arvel is the conventions-and-DX layer on top of the standard async-Python stack. The current locked stack (minimum floors from `packages/arvel/pyproject.toml`):

| Concern | Library |
|---|---|
| HTTP / ASGI | FastAPI 0.136+ / Starlette 1.0+ / Uvicorn 0.47+ |
| Validation / DTOs | Pydantic 2.13+ |
| Settings | pydantic-settings 2.14+ |
| ORM | SQLAlchemy 2.0+ (`Mapped`, `mapped_column`, asyncio) |
| Migrations | Alembic 1.18+ + custom Schema DSL wrapping it |
| Queue | Taskiq 0.12+ (Redis/AMQP brokers via optional extras) |
| Cache | redis-py 7.4+ (optional extra) |
| Templates | Jinja2 3.1+ |
| Serialization | msgspec 0.21+ |
| Observability | OpenTelemetry SDK + structlog 25.5+ |
| Crypto | cryptography 48+ |
| Hashing | argon2-cffi (default, core dep); bcrypt 5.0+ (opt-in extra) |
| CLI | Typer 0.25+ |
| Tests | pytest + pytest-asyncio + httpx |

## Consequences

- Arvel's identity is "conventions and DX over the standard stack", not "a from-scratch framework".
- Later ADRs take this stack as given.
- The performance budget is set against the *raw* libraries (≤ 5% overhead target).
- Positioning: "If you've used FastAPI and Pydantic, you already know most of Arvel."

## Current implementation

- Dependencies: `packages/arvel/pyproject.toml` (`[project] dependencies`, `[project.optional-dependencies]`).
- Architecture overview: `docs-fresh/architecture/overview.md`.

## Notes

- Hashing reconciled: `argon2-cffi` is a core dependency and the default; `bcrypt` is an opt-in extra. See ADR-084, which is being reconciled to match this layout.
