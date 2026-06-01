# ADR-015 — Two-tier middleware: Arvel Pipeline at route level, Starlette middleware at app level

**Date**: 2026-05-17
**Status**: Accepted
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.http.middleware`, `arvel.routing`

---

## Context

Arvel needs route-level middleware (Laravel: `Route::middleware(['throttle:60'])->get(...)`) and app-level middleware (Laravel: global kernel middleware). FastAPI provides app-level Starlette middleware natively, but per-route middleware in FastAPI is awkward (`Depends` chains, not `async def handle(request, call_next)`).

## Decision

**Two tiers, one shared `Middleware` Protocol.**

- **Route-level**: a `Middleware` Protocol with `handle(request, call_next)` semantics, run via `arvel.support.Pipeline`. Each route runs the pipeline before the handler.
- **App-level**: Starlette middleware directly, mounted on the FastAPI app for whole-request concerns (CORS, trusted host, etc.).

The shared Protocol means a user writes one shape; app-level usage adapts the Protocol to Starlette where needed.

```
Request ─► Starlette middleware stack (app-level: CORS, TrustedHost, …)
              │
              ▼
        FastAPI dispatcher
              │
              ▼
        Route-level Pipeline (Throttle → Authenticate → VerifyCsrf → handler)
              │
              ▼
           Handler
```

## Why two tiers

- **Pipeline at route level** is the right primitive for per-route configuration (throttle limits, auth guard, CSRF exceptions) and reuses the existing `Pipeline` — no new abstraction.
- **Starlette at app level** is the right primitive for lifecycle-wide concerns that don't care about routes (CORS, gzip, request ID). Wrapping those in the Pipeline would be reimplementation for no gain.

## Trade-offs

- Two execution paths mean subtly different debugging; the default exception handler reshapes traces.
- App-level middleware can't read the matched route (a Starlette constraint) — anything route-aware belongs in the route tier.

## Consequences

- `Cors` and similar are Starlette-flavored (app-level only). `Throttle`, `Authenticate`, `VerifyCsrf` are Pipeline middlewares (route-level, work inside groups).
- Each middleware is documented with its tier.

## Current implementation

- Code: `packages/arvel/src/arvel/http/_middleware_core.py` (`Middleware` Protocol, `Cors`), `packages/arvel/src/arvel/http/middleware/` (concrete middlewares), `arvel/support` Pipeline.
- Docs: `docs-fresh/http/middleware.md`.
