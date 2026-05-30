# Middleware

Middleware intercepts requests before they reach your handlers. Arvel ships middleware for authentication, rate-limiting, and CSRF protection. You can add your own for any cross-cutting concern.

Every request automatically gets an **Arvel request scope** — a per-request container available at `request.state.arvel`. This is wired by the framework and requires no configuration.

Arvel has **two tiers** of middleware. Knowing the difference will save you a lot of debugging.

| Layer | Where it runs | Lifetime | Best for |
|---|---|---|---|
| **App-level** (Starlette) | Wraps every request before FastAPI sees it | Configured once on the FastAPI app | CORS, request IDs, structured access logs |
| **Route-level** (Arvel pipeline) | Composed per route/group, runs after URL match | Composed per route | Authentication, throttling, CSRF, custom guards |

The two tiers exist because Starlette middleware can't see the matched route (the URL hasn't been resolved yet), so it's the wrong place for per-route concerns.

## Defining route-level middleware

A middleware is anything that implements the `Middleware` protocol:

```python
from typing import Any, Awaitable, Callable


class TimingMiddleware:
    async def handle(
        self,
        request: Any,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        import time
        start = time.monotonic()
        response = await call_next(request)
        response.headers["x-elapsed-ms"] = f"{(time.monotonic() - start) * 1000:.1f}"
        return response
```

`handle()` receives the live request and a `call_next` callable that runs the rest of the pipeline. Whatever you return becomes the response.

## Applying middleware to a route

Three places where middleware can attach:

### On a single route

```python
@Route.get("/admin", middleware=[Authenticate("web"), Authorize("admin")])
async def admin_dashboard(): ...
```

### On a group

```python
with Route.group(middleware=[Authenticate("web")]):
    @Route.get("/profile")
    async def profile(): ...

    @Route.get("/settings")
    async def settings(): ...
```

### Globally (every route)

```python
class HttpServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Route.use([TimingMiddleware()])
```

`Route.use([...])` registers middleware that wraps every route, in registration order.

## Middleware execution order

Route-level middleware runs outer-to-inner on the way in, inner-to-outer on the way out:

```
TimingMiddleware.handle()       ← outermost
    Authenticate.handle()       ← from group
        Throttle.handle()       ← from route
            handler()
        Throttle returns
    Authenticate returns
TimingMiddleware returns
```

Group middleware precedes route middleware. Outer-group middleware precedes inner-group middleware.

## Short-circuiting

A middleware can short-circuit the pipeline by returning a response without calling `call_next`:

```python
class MaintenanceMode:
    async def handle(self, request, call_next):
        if Config.of(AppConfig).maintenance_mode:
            return JSONResponse({"error": "down for maintenance"}, status_code=503)
        return await call_next(request)
```

## Middleware parameters

For middleware that takes runtime config, accept arguments in `__init__`:

```python
class Throttle:
    def __init__(self, limit: int, *, window: int = 60, store: ThrottleStore) -> None:
        self._limit = limit
        self._window = window
        self._store = store

    async def handle(self, request, call_next):
        key = request.client.host
        if await self._store.over(key, self._limit, self._window):
            return JSONResponse({"error": "too many requests"}, status_code=429)
        await self._store.increment(key)
        return await call_next(request)


# Use it:
with Route.group(middleware=[Throttle(60, store=InMemoryStore())]):
    ...
```

## Defining app-level (Starlette) middleware

App-level middleware uses Starlette's interface directly:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        import uuid
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
```

Register it during ASGI app construction:

```python
class HttpServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        self.app.add_middleware(RequestIdMiddleware)
```

## Built-in middleware

| Middleware | Purpose |
|---|---|
| `Authenticate(guard)` | Requires a logged-in user via the named guard. Returns 401 when unauthenticated. |
| `OptionalAuthenticate(guard)` | Resolves the user when present; anonymous requests proceed with `request.state.user = None`. |
| `Authorize(action, model=None)` | Runs the corresponding `Gate` / `Policy` |
| `Throttle(limit, window=60, store=...)` | Rate-limits by IP or user ID |
| `Csrf` | Validates the CSRF token on state-changing methods |
| `EnsureHttps` | 301-redirects HTTP to HTTPS |
| `Cors` | Adds CORS headers (app-level only) |
| `DatabaseTransaction` | Wraps the handler in a DB transaction; commits on 2xx, rolls back on 5xx |
| `SetLocaleMiddleware(supported, default)` | Negotiates `Accept-Language`, sets `request.state.locale`; user-preference override supported |
| `SecurityHeadersMiddleware` | Adds `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, and `Content-Security-Policy` headers on every HTTP response |
| `RoleMiddleware(role)` | Requires the user to hold the named role — 401 if unauthenticated, 403 if role absent. From `arvel-permission`. |
| `PermissionMiddleware(permission)` | Requires the user to hold the named permission — 401/403 as above. From `arvel-permission`. |
| `RoleOrPermissionMiddleware(value)` | Passes if the user holds the named role **or** the named permission. From `arvel-permission`. |

See the [Authentication](authentication.md), [CSRF](csrf.md), [Rate Limiting](rate-limiting.md), and [Roles & Permissions](permission.md) pages for details.

## Where to next?

- [Authentication](authentication.md) — the `Authenticate` middleware.
- [CSRF](csrf.md) — the `Csrf` middleware.
- [Rate Limiting](rate-limiting.md) — the `Throttle` middleware.
- [Roles & Permissions](permission.md) — the `RoleMiddleware`, `PermissionMiddleware`, and `RoleOrPermissionMiddleware` classes.
