# ADR-003 — HTTP Layer

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-24; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Route facade over FastAPI, OpenAPI opt-in, two-tier middleware, rate-limit store ABC, bridge exemption, security headers placement, default exception handler, scope middleware wiring.

## Why this is one ADR

The HTTP request path is one design — a Laravel-flavoured wrapper over Starlette/FastAPI. The eight decisions describe its individual joints, but the design reads as one when collected.

---

## § 1 — Route facade wraps FastAPI APIRouter, group state in a ContextVar stack

**Originally**: ADR-013 · Date: 2026-05-17

### Context

Laravel's `Route::get(...)` / `Route::group(...)` are module-level facades over a global `Router` singleton. Group state (prefix, middleware, name prefix) stacks during the `group(...)` callback and unstacks on exit. On FastAPI we had three shapes: use `APIRouter` directly with no facade; build a router from scratch on Starlette; or wrap `APIRouter` with a thin facade that buffers route declarations at import time and flushes them onto the `FastAPI` instance at boot.

### Decision

**Wrap `APIRouter`.** `arvel.routing.Router` wraps `fastapi.APIRouter`. The `Route` facade is a module-level proxy to a single `Router`. Group state lives in a `contextvars.ContextVar` stack so nested `Route.group(...)` calls compose correctly and stay async/thread-safe. At boot, the router walks buffered routes and registers them on the `FastAPI` app, composing paths, middleware (per-route + per-group, run through the Arvel `Pipeline`), and names from the group stack.

### Why this shape

- Keeps all of FastAPI's machinery (OpenAPI generation, DI, response validation).
- Group composition stays clean — no global mutable dict, no thread-safety surprises.
- Gives Laravel DX without forcing users to think about routers.
- Leaves room for `Route.resource` / `Route.controller` later without changing the mounting.

Direct `APIRouter` was rejected because it doesn't compose group state through context managers and only offers `Depends`-style per-route middleware (not the `await call_next(request)` shape we want). Building from scratch on Starlette was rejected because it loses FastAPI's OpenAPI and ecosystem (constitution Article II.1: integrate, don't replace).

### Consequences

- Routes are buffered until boot registers them on the `FastAPI` app. Importing `bootstrap/app.py` is side-effect-free except for buffering — nothing hits the network.
- Route declaration is import-time only; declaring routes from a background thread without the right context lands them at the root group.
- Tests can reset the router to clear buffered routes between cases.

### Current implementation

- Code: `packages/arvel/src/arvel/routing/`, registered at boot by `arvel/providers/http_provider.py`.
- Docs: `docs/http/routing.md`.

---

## § 2 — Resource OpenAPI schemas are opt-in via ClassVar, not AST introspection

**Originally**: ADR-014 · Date: 2026-05-17

### Context

`JsonResource[T]` shapes a response via a `to_dict(request)` method. FastAPI needs a `response_model` to document the shape in OpenAPI. Options: infer the schema from `to_dict` by AST introspection (brittle); always emit `dict[str, object]` (accurate, useless for client codegen); or an opt-in `ClassVar` schema pointing at a Pydantic model.

### Decision

**Opt-in `ClassVar` schema.** A `JsonResource[T]` subclass MAY declare a class-level `schema: ClassVar[type[BaseModel]]`. If present, FastAPI gets that schema as the response model; if absent, the response is typed as `dict[str, object]`. The resource-collection variant reuses the same mechanism, wrapping the declared schema in a `{ "data": list[schema] }` envelope.

```python
class UserPublic(BaseModel):
    id: int
    email: EmailStr

class UserResource(JsonResource[User]):
    schema: ClassVar[type[BaseModel]] = UserPublic

    def to_dict(self, request: Request) -> dict[str, object]:
        return UserPublic(id=self.resource.id, email=self.resource.email).model_dump()
```

### Why opt-in

- AST introspection breaks on any `if/else`, comprehension, or method call in `to_dict`, and would be silently wrong for OpenAPI consumers.
- `dict[str, object]` as the default keeps the contract honest: no declared shape, no schema claim.
- The `ClassVar` is purely declarative — no decorators, no metaclass — and both strict checkers handle `ClassVar[type[BaseModel]]` with no special casing.

### Trade-off accepted

Slightly more verbose than magical inference: developers write the Pydantic schema explicitly. The constitution (Article VIII.1) values predictability over magic. Resources without a schema produce uninformative OpenAPI — a documented trade-off, not a bug.

### Current implementation

- Code: `packages/arvel/src/arvel/http/resources.py`.
- Docs: `docs/http/resources.md`.

---

## § 3 — Two-tier middleware: Arvel Pipeline at route level, Starlette middleware at app level

**Originally**: ADR-015 · Date: 2026-05-17

### Context

Arvel needs route-level middleware (Laravel: `Route::middleware(['throttle:60'])->get(...)`) and app-level middleware (Laravel: global kernel middleware). FastAPI provides app-level Starlette middleware natively, but per-route middleware in FastAPI is awkward (`Depends` chains, not `async def handle(request, call_next)`).

### Decision

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

### Why two tiers

- **Pipeline at route level** is the right primitive for per-route configuration (throttle limits, auth guard, CSRF exceptions) and reuses the existing `Pipeline` — no new abstraction.
- **Starlette at app level** is the right primitive for lifecycle-wide concerns that don't care about routes (CORS, gzip, request ID). Wrapping those in the Pipeline would be reimplementation for no gain.

### Trade-offs

- Two execution paths mean subtly different debugging; the default exception handler reshapes traces.
- App-level middleware can't read the matched route (a Starlette constraint) — anything route-aware belongs in the route tier.

### Consequences

- `Cors` and similar are Starlette-flavored (app-level only). `Throttle`, `Authenticate`, `VerifyCsrf` are Pipeline middlewares (route-level, work inside groups).
- Each middleware is documented with its tier.

### Current implementation

- Code: `packages/arvel/src/arvel/http/_middleware_core.py` (`Middleware` Protocol, `Cors`), `packages/arvel/src/arvel/http/middleware/` (concrete middlewares), `arvel/support` Pipeline.
- Docs: `docs/http/middleware.md`.

---

## § 4 — Rate-limit store is a Protocol with InMemory + Redis drivers, container-resolved

**Originally**: ADR-016 · Date: 2026-05-17 · Status: Accepted (interface reconciled — Protocol, not ABC)

### Context

The `Throttle` middleware needs to record attempt counts per key. Options: hard-code in-memory (simple, wrong in production); hard-code Redis (forces a Redis dependency in dev/test); or a pluggable store interface resolved through the container.

### Decision

**Pluggable store interface, container-resolved.** The store contract is a `typing.Protocol` (consistent with ADR-009 § 1), not an ABC:

```python
@runtime_checkable
class RateLimiterStore(Protocol):
    async def hit(self, key: str, *, decay_seconds: int) -> Attempt: ...

@dataclass(frozen=True, slots=True)
class Attempt:
    count: int
    reset_at: datetime
```

Two built-in drivers:
- `InMemoryStore` — process-local dict + `asyncio.Lock`. The default binding.
- `RedisStore` — wraps a Redis client (lazy import; needs `arvel[redis]`). Hashes keys (SHA-256) and uses `INCR` + `EXPIRE`; tolerates sync or async client methods.

`HttpServiceProvider.register()` binds `RateLimiterStore → InMemoryStore` by default. Users swap to Redis (or any custom store) by binding their own implementation of the Protocol in a provider.

### Why a Protocol

- Tests use a fake store without touching Redis.
- Enterprise users plug in Memcached/DynamoDB drivers later.
- Container binding makes the swap declarative — no Laravel-style string driver config.

`Throttle` is not coupled to the Cache subsystem: the `hit()` method is async so both sync (in-memory) and async (Redis) backends present one uniform interface.

### Consequences

- One public type per driver; `RateLimiterStore` is the Protocol.
- `decay_seconds` is keyword-only; `Attempt` is an immutable dataclass carrying the current `count` and `reset_at`.

### Current implementation

- Code: `packages/arvel/src/arvel/http/ratelimit.py`; default binding in `packages/arvel/src/arvel/providers/http_provider.py`.
- Docs: `docs/http/middleware.md`.

### Notes

- **Reconciled from the original**: the title and body said "ABC"; the shipped contract is a `Protocol`. The earlier draft also described a `RATE_LIMIT_STORE` env var, automatic Redis binding, and a boot-time `RuntimeWarning` for non-local environments — **none of that is implemented**. The provider binds `InMemoryStore`; Redis is opt-in by binding it yourself. The `redis>=5.2` floor referenced in the original is now `redis>=7.4` (see ADR-001 § 4 extras).

---

## § 5 — Sanctioned http→database exemption for `DatabaseTransaction` middleware

**Originally**: ADR-017 · Date: 2026-05-17

### Context

The ORM ships a request-scoped transaction middleware so handlers get
automatic commit-on-2xx / rollback-on-exception semantics. The natural place
for this middleware is `arvel.http.middleware.database_transaction`, because
it's an HTTP middleware. But the forbidden-import rule
(`tests/architecture/test_layering.py`) prohibits `arvel.http.*` from
importing `arvel.database.*` symbols.

Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Ship the middleware in `arvel.database.middleware` instead | No exemption needed | Hides an HTTP-layer concept from where developers expect it; `arvel.database.*` then has to know about Starlette `BaseHTTPMiddleware` (a different layering violation) |
| B. Resolve the session via `Application.container.amake(AsyncSession)` inside the middleware, importing only `arvel.container` types | No direct database import | The middleware still depends on `AsyncSession` being a SQLA type; renaming the type is felt across the http boundary |
| C. **Named exemption — explicitly allow `arvel.http.middleware.database_transaction` to import `arvel.database`** | Honest: the dependency is real and intentional | One hand-maintained allowlist entry |

### Decision

Option C. The forbidden-import test maintains a short allowlist with comments:

```python
## tests/architecture/test_layering.py
ALLOWED_HTTP_TO_DATABASE_IMPORTS = {
    # The DatabaseTransaction middleware bridges HTTP request lifecycle to
    # ORM session lifecycle. This is a sanctioned exception (ADR-003 § 5) — it
    # exists because the middleware is conceptually HTTP-flavoured (responds
    # to request/response events) but operates on an ORM primitive.
    "arvel.http.middleware.database_transaction": {
        "arvel.database",
        "sqlalchemy.ext.asyncio",
    },
}
```

Every other `arvel.http.*` module is forbidden from importing `arvel.database.*`.
Every `arvel.database.*` module is forbidden from importing `arvel.http.*`
(no exemption in that direction — the database layer must not know about HTTP).

### Consequences

**Positive**:
- The middleware lives where developers expect it (HTTP middleware in
  `arvel.http.middleware`).
- The exemption is one named entry with a comment, easy to audit.
- The forbidden-import test is the canonical source of truth — adding a
  second exemption requires editing the same file and writing a justification.

**Negative**:
- Future contributors might try to expand the exemption casually. We mitigate
  via code review: any new entry in `ALLOWED_HTTP_TO_DATABASE_IMPORTS`
  requires an ADR (or extension of this one).

**Enforcement**:
- The forbidden-import test asserts: every `arvel.http.*` module not in
  `ALLOWED_HTTP_TO_DATABASE_IMPORTS` must not import `arvel.database.*`.
- New entries to the allowlist require an ADR.

### Current implementation

- Middleware: `packages/arvel/src/arvel/http/middleware/database_transaction.py`.
- Layering guard: `packages/arvel/tests/architecture/` (forbidden-import test).
- Docs: `docs/http/middleware.md`, `docs/orm/model-internals.md`.

---

## § 6 — `SecurityHeadersMiddleware` — pure-ASGI, in `arvel.http.middleware`

**Originally**: ADR-018 · Date: 2026-05-24

### Context

The demo shipped a local `SecurityHeadersMiddleware` copy. Every production Arvel app should apply the same security headers without copying code.

### Decision

Ship `SecurityHeadersMiddleware` in `arvel.http.middleware.security_headers` as a **pure-ASGI** middleware (not `BaseHTTPMiddleware`). It injects four headers on every HTTP response:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; form-action 'self'
```

All headers use `setdefault` semantics — handler-set values are never overwritten. WebSocket and lifespan scopes pass through unmodified. Every value is configurable via constructor kwargs; `csp=None` suppresses the CSP header, and `path_csp_overrides` maps path prefixes to a per-path CSP (longest matching prefix wins) — useful for serving Swagger UI under a looser policy without weakening the global default.

### Rationale

- **Pure ASGI over `BaseHTTPMiddleware`**: `BaseHTTPMiddleware` buffers the whole response body, breaking `Content-Length` on streaming responses and adding latency. Pure ASGI hooks `http.response.start` directly.
- **`arvel.http.middleware`** is the right home — security headers are a cross-cutting HTTP concern, not tied to auth/i18n/cache.
- **`setdefault`** preserves a route's own headers (e.g. a nonce-based CSP).
- **`frame-ancestors 'none'`** prevents clickjacking; a safe default for APIs and most web apps.

### Current implementation

- Code: `packages/arvel/src/arvel/http/middleware/security_headers.py` (defaults: `_DEFAULT_HSTS_MAX_AGE`, `_DEFAULT_CSP`, `_DEFAULT_REFERRER_POLICY`).
- Docs: `docs/http/middleware.md`.

### Notes

- **Reconciled**: the shipped default CSP is `default-src 'self'; frame-ancestors 'none'; form-action 'self'` (the original ADR omitted `form-action 'self'`). The `csp=None` and `path_csp_overrides` knobs were added after the original.

---

## § 7 — HttpExceptionHandler as Default Error Handler

**Originally**: ADR-019 · Date: 2026-05-24

### Context

`HttpServiceProvider` bound `ProblemDetailsHandler` as the default exception handler,
producing RFC 7807 `{type, title, status, detail}` envelopes. The documented and tested
contract is `{error: {code, message, details?}}`. Tests worked only because they manually
registered `HttpExceptionHandler`.

### Decision

`HttpServiceProvider` binds `HttpExceptionHandler` as the default. `ProblemDetailsHandler`
stays available as an opt-in import for projects that prefer RFC 7807.

### Consequences

- All HTTP error responses — including validation, auth, 404, and 500 — use one shape
- Frontend clients need only one error handler
- Projects that prefer RFC 7807 opt back in by binding `ProblemDetailsHandler` (which subclasses `HttpExceptionHandler`)

### Current implementation

- Default binding: `packages/arvel/src/arvel/providers/http_provider.py` binds `HttpExceptionHandler` (with the default foreign-exception translators).
- Opt-in RFC 7807: `packages/arvel/src/arvel/http/problem_details.py` (`ProblemDetailsHandler`, bound as a singleton override).
- Docs: `docs/http/exceptions.md`.

---

## § 8 — ArvelScopeMiddleware Wired in into_asgi()

**Originally**: ADR-020 · Date: 2026-05-24

### Context

`arvel.dep()` requires `request.state.arvel_scope`, but no middleware created it. Using `Depends(dep(MyService))` in a FastAPI route raised `AttributeError`.

### Decision

`Application.into_asgi()` unconditionally mounts `ArvelScopeMiddleware` (passing the application container). The middleware:

1. Opens a per-request child scope from the container (`ascope()`).
2. Stores it at `request.state.arvel_scope`.
3. Tears it down in a `finally` block after the response is sent.

### Consequences

- Per-request DI is turnkey — no manual setup.
- Scoped singletons (e.g. DB sessions) are isolated per request.
- Overhead is ~one container scope per request — negligible.
- Tests that previously faked `SimpleNamespace(arvel_scope=...)` work against a real scope.

### Current implementation

- Code: `packages/arvel/src/arvel/http/middleware/scope.py` (`ArvelScopeMiddleware`); mounted in `packages/arvel/src/arvel/application/application.py::into_asgi()`.
- Docs: `docs/architecture/ARCH-002-bootstrap-lifecycle.md`, `docs/architecture/ARCH-003-service-container.md`.

### Notes

- **Reconciled**: the original called this the "outermost middleware layer". It is mounted in `into_asgi()`, but Starlette's `add_middleware` prepends, and later additions (maintenance-mode, context, deferred-task middleware) wrap outside it. The guarantee that holds is: it runs for every request and establishes the per-request scope before route handlers resolve `dep(...)`. Exact layer ordering is documented in the bootstrap lifecycle.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-013 | 2026-05-17 | Route facade wraps FastAPI APIRouter, group state in a ContextVar stack | § 1 |
| ADR-014 | 2026-05-17 | Resource OpenAPI schemas are opt-in via ClassVar, not AST introspection | § 2 |
| ADR-015 | 2026-05-17 | Two-tier middleware: Arvel Pipeline at route level, Starlette middleware at app level | § 3 |
| ADR-016 | 2026-05-17 | Rate-limit store is a Protocol with InMemory + Redis drivers, container-resolved | § 4 |
| ADR-017 | 2026-05-17 | Sanctioned http→database exemption for `DatabaseTransaction` middleware | § 5 |
| ADR-018 | 2026-05-24 | `SecurityHeadersMiddleware` — pure-ASGI, in `arvel.http.middleware` | § 6 |
| ADR-019 | 2026-05-24 | HttpExceptionHandler as Default Error Handler | § 7 |
| ADR-020 | 2026-05-24 | ArvelScopeMiddleware Wired in into_asgi() | § 8 |
