# ADR-001 — Adopt FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq as the framework stack

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous), ratified by user "ACT"
**Scope**: Whole framework (constitution Article II)

---

## Context

Arvel is a Laravel-style web framework for Python. The first architectural choice — and the one that constrains every other decision — is what underlying libraries to integrate with versus replace. Existing Python frameworks have made varied choices:

- **Django** rebuilt its own ORM, templating, forms, admin.
- **Masonite** rebuilt its own router, ORM, container.
- **Uvicore** kept FastAPI but rebuilt the ORM on SQLAlchemy Core.
- **LaraFastAPI / SwX-API / Apiary / Zenith** layered scaffolding on FastAPI without replacing core libs.

We need to commit one way or the other before writing a single line of framework code.

## Options considered

### Option A — Build our own ORM/router/validation (Masonite path)

**Pros**: Total control; Laravel-faithful naming/behavior.
**Cons**: Decades of work to reach SQLAlchemy/FastAPI/Pydantic parity; we'd be the only ones maintaining a major ORM in 2026 Python; non-typed; non-standard; community would distrust it.

### Option B — Integrate FastAPI + Pydantic + SQLAlchemy + Alembic + Taskiq + Redis + Jinja2 (chosen)

**Pros**:
- Ride the strongest async-Python ecosystem.
- Inherit type-safety from Pydantic and SQLAlchemy (`Mapped[T]`, `BaseModel`).
- Free OpenAPI generation from FastAPI.
- Free async DB + migration story from SQLAlchemy + Alembic.
- Free async queue from Taskiq (the fastest async queue in our benchmark research).
- Standard hashing, crypto, logging libraries.
- Contributors already know these libraries.

**Cons**:
- Tied to the major-version cadence of 4–5 libraries (SemVer discipline mitigates).
- Some Laravel-specific UX requires creative wrappers (e.g., Eloquent's `where("name", "x")` translates to `where(Model.name == "x")`).
- We have to design integration carefully to avoid leaking each lib's quirks.

### Option C — Adopt Litestar instead of FastAPI

**Pros**: Better DI baked in; "batteries-included"; ~2× throughput on synthetic benchmarks.
**Cons**: Smaller community, fewer integrations, less OpenAPI tooling, less typed-Pydantic-native than FastAPI in 2026. Laravel's audience and ours overlap heavily with the FastAPI audience; choosing Litestar would be a marketing mismatch.

## Decision

**Option B.** Stack locked in Constitution Article II:

| Concern | Library |
|---|---|
| HTTP | FastAPI 0.115+ / Starlette / Uvicorn |
| Validation / DTOs | Pydantic |
| Settings | pydantic-settings v2 |
| ORM | SQLAlchemy (`Mapped`, `mapped_column`) |
| Migrations | Alembic + custom Schema DSL wrapping it |
| Queue | Taskiq (Redis broker default) |
| Cache | redis-py async |
| Templates | Jinja2 |
| Logging | structlog |
| Hashing | argon2-cffi (default), bcrypt (compat) |
| CLI | Typer |
| Tests | pytest + pytest-asyncio + httpx |

## Consequences

- Arvel's identity is "the conventions and DX layer on top of the standard async-Python stack" — not "a from-scratch framework".
- Every later ADR can take this stack as given.
- Performance budget (NFR-001-001/002) is set against the *raw* version of these libs; ≤ 5% overhead target.
- Marketing positioning: "If you've used FastAPI and Pydantic, you already know 80% of Arvel."

## References

- `docs/BRAINSTORM.md` §2 (decision rationale per concern).
- Research findings on Litestar vs FastAPI, ARQ vs Taskiq, Masonite vs Uvicore vs LaraFastAPI.
