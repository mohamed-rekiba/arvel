# ADR-093 — create_test_app() as async context manager

**Date**: 2026-05-23
**Status**: Accepted

## Context

The demo uses a `StarterApp` class (wrapping `Application` + `FastAPI`) with manual
`create_app()` + `await app.shutdown()` in test fixtures. Two alternatives were considered:
- Keep the class-based approach with explicit `async with`-like lifecycle
- Use an `AsyncContextManager` via `@asynccontextmanager`

## Decision

`create_test_app()` is an `@asynccontextmanager` that yields an `httpx.AsyncClient`.

## Rationale

The context manager pattern is cleaner for test fixtures: `async with create_test_app(...)
as client:` eliminates the explicit shutdown call and makes it impossible to forget teardown.
The `httpx.AsyncClient` as the yielded value means tests directly interact with the client
without accessing the wrapper object.

ASGI types use `starlette.types.Scope`, `Receive`, `Send` (not `Any`) to satisfy `mypy
--strict` without suppressions.

## Consequences

- `app/bootstrap.py` `StarterApp` class and `create_app()` are deleted after migration
- Tests must use `async with create_test_app(...) as client:` idiom
- `create_test_app` exported from `arvel.testing` (not `arvel` root — production code guard)
