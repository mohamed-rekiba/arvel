# ADR-112: ArvelScopeMiddleware Wired in into_asgi()

**Status**: Accepted
**Date**: 2026-05-24

## Context

`arvel.dep()` required `request.state.arvel_scope` but no middleware created it. Using
`Depends(dep(MyService))` in any FastAPI route raised `AttributeError`.

## Decision

`Application.into_asgi()` unconditionally mounts `ArvelScopeMiddleware` (Starlette-compatible)
as the outermost middleware layer. The middleware:
1. Calls `container.ascope()` to create a per-request child scope
2. Stores it at `request.state.arvel_scope`
3. Tears it down in a `finally` block after the response is sent

## Consequences

- Per-request DI is turnkey — no manual setup required
- Scoped singletons (e.g., DB sessions) are correctly isolated per request
- Minor overhead (~1 container scope creation per request) is negligible
- Existing tests that used `SimpleNamespace(arvel_scope=...)` now work with real scope
