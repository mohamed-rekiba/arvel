# ADR-012 — create_test_app() as async context manager

**Date**: 2026-05-23
**Status**: Accepted
**Last reconciled**: 2026-06-01

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

- The demo's `StarterApp` class and `create_app()` are removed in favor of the context manager
- Tests use the `async with create_test_app(...) as client:` idiom
- `create_test_app` is exported from `arvel.testing` (not `arvel` root — production-code guard)

## Current implementation

- Code: `packages/arvel/src/arvel/testing/app.py` (yields `httpx.AsyncClient`, boots on entry, shuts down on exit via `finally`; the bootable app is a `Protocol`).
- Docs: `docs-fresh/contributing/testing.md`.
