# ADR-008 — Two-tier middleware: Arvel Pipeline at route level, Starlette middleware at app level

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.http.middleware`, `arvel.routing`

---

## Context

We need middleware that supports route-level attachment (Laravel: `Route::middleware(['throttle:60'])->get(...)`) AND app-level attachment (Laravel: `Kernel::$middleware` global). FastAPI provides app-level Starlette middleware natively. Per-route middleware in FastAPI is awkward (`Depends` chains, not `async def handle(request, call_next)`).

Options:
1. Build everything on Starlette middleware — but Starlette middleware is app-level by design; route-level requires per-route wrappers.
2. Build everything on FastAPI `Depends` — loses the `call_next` shape and the per-request response transformation.
3. Adopt a `Middleware` Protocol with `handle(request, call_next)` semantics, run via `arvel.support.Pipeline`, and **only** at the route level. Use Starlette middleware unchanged for app-level concerns (CORS in production, TrustedHost, etc.).

## Decision

Adopt option 3.

- **Route-level**: `Middleware` Protocol + `Pipeline` (reuse from foundations). Each route gets an injected `Depends` that runs the Pipeline before calling the handler.
- **App-level**: Starlette middleware directly. The `HttpServiceProvider` mounts well-known wrappers (CORS, CSRF as a Starlette middleware adapter) on the FastAPI app.

The two tiers share the same `Middleware` Protocol so a user can write a class once and use it at either level. The app-level path adapts the Protocol to a Starlette `BaseHTTPMiddleware` via a tiny adapter (`arvel.http.middleware._starlette_adapter.adapt(middleware)`).

```
Request ─► Starlette middleware stack (app-level: CORS, TrustedHost, custom)
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

- **Pipeline at route level** = the right primitive for "things that need per-route configuration" (throttle limits per route, auth guard per route, CSRF exceptions per route). Reusing the existing `Pipeline` from foundations means no new abstractions.
- **Starlette at app level** = the right primitive for "things that wrap the whole request lifecycle and don't care about routes" (CORS, gzip, request ID). Wrapping these in our Pipeline would be re-implementation for no win.
- The shared Protocol means the user-facing learning curve is one shape, even though there are two execution paths.

## Trade-offs

- Two execution paths means subtly different debugging — the stack trace on a 500 is wider when the failure is in route-level middleware. Mitigated by `HttpExceptionHandler` re-shaping traces.
- App-level middlewares can't read the matched route. That's a Starlette constraint we inherit; OK because anything route-aware belongs in the route tier anyway.

## Consequences

- The `Cors`, `TrustProxies`, and similar middlewares are exposed as **Starlette wrappers** (subclasses of `BaseHTTPMiddleware`). They're public in `arvel.http.middleware` but documented as "app-level only".
- `Throttle`, `Authenticate`, `VerifyCsrf` are exposed as **Pipeline middlewares**. Public in `arvel.http.middleware`, documented as "route-level (works inside groups too)".
- Documentation must label each middleware with its tier — single-source-of-truth lives in the API reference.

---

## Cross-references

- PRD-002: FR-002-013, FR-002-014, FR-002-015, FR-002-017, FR-002-020
- SAD-002 §3 (Middleware component)
