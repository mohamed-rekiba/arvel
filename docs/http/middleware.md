# Middleware

Arvel has **two tiers** of middleware. Knowing which tier a class belongs to tells you where it runs and how it composes.

**Source**: `packages/arvel/src/arvel/http/_middleware_core.py`, `http/middleware/`, `context/middleware.py`, and the stack assembly in `application/application.py`.

| Tier | Mechanism | Runs |
|---|---|---|
| **App-level (ASGI)** | `FastAPI.add_middleware(...)` | for every request, before route matching |
| **Route-level** | `Middleware` protocol + `arvel.support.Pipeline` | only on routes that declare it, after route matching |

```mermaid
flowchart TB
    Req["request"] --> ASGI["App-level ASGI middleware<br/>(outer → inner)"]
    ASGI --> Match["FastAPI route matching"]
    Match --> Pipe["Route-level Pipeline middleware<br/>(per RouteSpec.middleware)"]
    Pipe --> Handler["handler / controller"]
```

## Route-level: the `Middleware` protocol

Route middleware implements a single async method:

```python
@runtime_checkable
class Middleware(Protocol):
    async def handle(self, request: Any, call_next: CallNext) -> Any: ...

CallNext = Callable[[Any], Awaitable[Any]]
```

`_wrap_with_middleware` (in `routing.py`) adapts each `Middleware` into an `arvel.support.Pipeline` step. The pipeline runs left-to-right — the **first** middleware in the tuple is the outermost on the request path:

```python
return await Pipeline().send(request).through(pipeline_steps).then(final)
```

Route middleware comes from three places, merged in order: enclosing `Route.group(middleware=[...])` frames, named groups resolved from strings, and the route's own `middleware=[...]`.

### Built-in route middleware

| Class | Module | Behavior |
|---|---|---|
| `Authenticate(guard_name="web")` | `_middleware_core.py` | Resolves `AuthManager.guard(name)`, sets `request.state.user`, raises `UnauthenticatedException` if none. |
| `Throttle(max_attempts, *, decay_seconds=60, key=None, store=None)` | `_middleware_core.py` | Rate limit; raises `ThrottleException` (429) past the limit. |
| `VerifyCsrf(except_paths=None)` | `_middleware_core.py` | Double-submit CSRF check; raises `CsrfMismatchException` (419). |
| `SignedMiddleware` | `middleware/signed.py` | Verifies `URL.has_valid_signature(request)`. |
| `DatabaseTransaction(session_maker=None)` | `middleware/database_transaction.py` | Wraps the request in a DB transaction (and provides the active session that `exists`/`unique` validation rules need). |

`Authenticate` resolves the guard at request time:

```python
async def handle(self, request, call_next):
    manager = container.make(AuthManager)
    guard = manager.guard(self._guard_name)
    user = await guard.user(request)
    if user is None:
        raise UnauthenticatedException("Not authenticated.")
    request.state.user = user
    _bind_user_to_context(user)
    return await call_next(request)
```

## App-level: ASGI middleware

These wrap the whole FastAPI app via `add_middleware`. The stack is **declared**, not hardcoded: `into_asgi()` walks the app's `bootstrap/middleware.py` list (or `_default_middleware_stack()` when none is declared) and calls each entry's `boot(app, container)`. Each entry is a `GlobalMiddleware` (`arvel.contracts.middleware`) — see [Global ASGI Middleware](../site/the-basics/middleware.md#global-middleware-stack) for the app-author view.

| Class | Module | In default stack? | Role |
|---|---|---|---|
| `TrustProxiesMiddleware` | `middleware/trust_proxies.py` | yes (if `TRUSTED_PROXIES` set) | Rewrites client IP/scheme/host from `X-Forwarded-*`. |
| `MaintenanceModeMiddleware` | `maintenance` | yes (if manager bound) | 503s while in maintenance mode. |
| `ThrottleLoginMiddleware` | `auth/middleware/throttle_login.py` | yes (if auth + rate limiting) | Throttles login attempts. |
| `CsrfDoubleSubmitMiddleware` | `auth/middleware/csrf_double_submit.py` | yes (if auth + CSRF) | Cookie double-submit CSRF check. |
| `ObservabilityMiddleware` | `observability` | yes (when configured) | Request tracing/logging. |
| `ContextMiddleware` | `context/middleware.py` | yes (with observability) | Per-request context repository. |
| `DeferredTaskMiddleware` | `context/middleware.py` | yes (with observability) | Drains `defer()`'d tasks after the response. |
| `ArvelScopeMiddleware` | `middleware/scope.py` | yes — **pinned innermost** | Sets `request.state.arvel_scope` (the container `dep()` reads). |
| `Cors` | `_middleware_core.py` | no | CORS (subclasses Starlette `CORSMiddleware`). |
| `MethodSpoofMiddleware` | `middleware/method_spoof.py` | no | Rewrites POST + `_method=PUT/PATCH/DELETE` (must run before routing). |
| `SecurityHeadersMiddleware` | `middleware/security_headers.py` | no | HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy`. |

The "if …" qualifiers mean the middleware is *in the default list* but **self-gates** in its `boot()` — it only mounts when its config applies. So listing one is always safe.

> **Warning**: `Cors`, `MethodSpoofMiddleware`, and `SecurityHeadersMiddleware` aren't `GlobalMiddleware` subclasses and aren't in the default stack. Mount them explicitly with `app.add_middleware(...)`, or wrap them in a `GlobalMiddleware` to add them to the declared list.

## Stack ordering

The declared list is **outer→inner** — the first entry is the outermost layer. `add_middleware` prepends, so `_mount_middleware` boots the resolved chain in **reverse** to make the list order hold:

```python
# application.py
declared = self._middleware_classes or _default_middleware_stack()
chain = _resolve_middleware_chain(declared)  # ArvelScope pinned last (innermost)
for mw_cls in reversed(chain):
    mw_cls.boot(fa, self.container)           # each entry self-gates + add_middleware
```

`_resolve_middleware_chain` dedupes and always appends `ArvelScopeMiddleware` as the innermost layer, regardless of where (or whether) the app lists it — the per-request DI scope must wrap the handler.

Resulting request path for the default stack (outer → inner), when all layers are active:

```mermaid
flowchart LR
    T["TrustProxies"] --> M["Maintenance"] --> TL["ThrottleLogin"] --> CS["CsrfDoubleSubmit"] --> O["Observability"] --> C["Context"] --> D["DeferredTask"] --> S["ArvelScope"] --> R["FastAPI routing"] --> P["per-route Pipeline"] --> H["handler"]
```

> **Note**: `ContextMiddleware` and `DeferredTaskMiddleware` live under `arvel.context`, not `arvel.http`, even though they're part of the default stack.

## Choosing a tier

- Cross-cutting concern for the whole app, needs to run before routing, or is a third-party ASGI middleware → **app-level** (`add_middleware`).
- Per-route concern (auth, throttling, CSRF, transactions) that needs the matched route and `call_next` semantics → **route-level** (`Middleware` protocol).

See [extending Arvel](../contributing/extending.md) for writing a new middleware.
