# ADR-020: ArvelScopeMiddleware Wired in into_asgi()

**Status**: Accepted
**Date**: 2026-05-24
**Last reconciled**: 2026-06-01

## Context

`arvel.dep()` requires `request.state.arvel_scope`, but no middleware created it. Using `Depends(dep(MyService))` in a FastAPI route raised `AttributeError`.

## Decision

`Application.into_asgi()` unconditionally mounts `ArvelScopeMiddleware` (passing the application container). The middleware:

1. Opens a per-request child scope from the container (`ascope()`).
2. Stores it at `request.state.arvel_scope`.
3. Tears it down in a `finally` block after the response is sent.

## Consequences

- Per-request DI is turnkey — no manual setup.
- Scoped singletons (e.g. DB sessions) are isolated per request.
- Overhead is ~one container scope per request — negligible.
- Tests that previously faked `SimpleNamespace(arvel_scope=...)` work against a real scope.

## Current implementation

- Code: `packages/arvel/src/arvel/http/middleware/scope.py` (`ArvelScopeMiddleware`); mounted in `packages/arvel/src/arvel/application/application.py::into_asgi()`.
- Docs: `docs-fresh/architecture/bootstrap-lifecycle.md`, `docs-fresh/architecture/service-container.md`.

## Notes

- **Reconciled**: the original called this the "outermost middleware layer". It is mounted in `into_asgi()`, but Starlette's `add_middleware` prepends, and later additions (maintenance-mode, context, deferred-task middleware) wrap outside it. The guarantee that holds is: it runs for every request and establishes the per-request scope before route handlers resolve `dep(...)`. Exact layer ordering is documented in the bootstrap lifecycle.
