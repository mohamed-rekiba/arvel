# Middleware

<a name="introduction"></a>
## Introduction

Middleware provides a convenient mechanism for inspecting and filtering HTTP requests entering your application. For example, Arvel includes middleware that verifies the user of your application is authenticated. If the user is not authenticated, the middleware redirects the request to a `401` response. However, if the user is authenticated, the middleware allows the request to proceed deeper into the application.

Arvel has two kinds of middleware:

- **Route middleware** runs in a per-route pipeline around your handler. It implements a simple protocol: an async `handle(self, request, call_next)` method.
- **Application (ASGI) middleware** wraps the entire application at the ASGI layer — CORS, security headers, and so on.

This page focuses on route middleware, then covers the application layer.

<a name="defining-middleware"></a>
## Defining Middleware

A route middleware is any object that implements an async `handle` method taking the request and a `call_next` callable. Calling `call_next(request)` passes control to the next middleware (or, eventually, your handler) and returns its response:

```python
from arvel import BadRequestException


class EnsureTokenIsValid:
    async def handle(self, request, call_next):
        if request.headers.get("X-Token") != "secret":
            raise BadRequestException("Invalid token.")
        return await call_next(request)
```

<a name="before-and-after-middleware"></a>
### Before and After Middleware

Whether a middleware runs *before* or *after* the request is handled depends on the middleware itself. Code before `call_next` runs on the way in; code after it runs on the way out:

```python
import time


class TimeRequests:
    async def handle(self, request, call_next):
        start = time.perf_counter()          # before
        response = await call_next(request)
        elapsed = time.perf_counter() - start  # after
        return response
```

Multiple middleware compose outer-to-inner: the first middleware listed runs first on the way in and last on the way out.

<a name="short-circuiting-a-request"></a>
### Short-Circuiting a Request

To stop a request from reaching your handler, return a response (or raise an exception) **without** calling `call_next`:

```python
from arvel import AuthorizationException


class BlockBannedIps:
    async def handle(self, request, call_next):
        if is_banned(request.client.host):
            raise AuthorizationException("Forbidden.")
        return await call_next(request)
```

<a name="registering-middleware"></a>
## Registering Middleware

<a name="assigning-to-routes"></a>
### Assigning to Routes

Assign middleware to a route by passing instances (or [named-group strings](#middleware-groups-named)) to the `middleware` keyword:

```python
from arvel.http.middleware import Authenticate, Throttle


@Route.get("/api/me", middleware=[Authenticate("api"), Throttle(60)])
async def me(request) -> dict:
    return {"user_id": request.state.user.id}
```

<a name="assigning-to-groups"></a>
### Assigning to Groups

Attach middleware to every route in a [route group](routing.md#route-groups):

```python
with Route.group(prefix="/api", middleware=[Authenticate("api")]):
    @Route.get("/profile")
    async def profile(request) -> dict:
        ...
```

<a name="middleware-groups-named"></a>
### Middleware Groups (Named)

Register a named middleware group on the router so routes can reference it by string. Define groups from a [route service provider](routing.md#registering-routes-from-a-provider):

```python
class AppRouteServiceProvider(RouteServiceProvider):
    def map_routes(self, router: Router) -> None:
        router.middleware_group("api", [Throttle(60), Authenticate("api")])
```

Routes opt in with the group's name:

```python
@Route.get("/api/posts", middleware=["api"])
async def posts() -> list[dict]:
    ...
```

Named groups can include other named groups; they're expanded recursively with cycle detection.

> [!NOTE]
> There's no global middleware stack and no kernel-style priority list. Ordering is the order of the middleware tuple, composed left-to-right. Build the order you want explicitly per route or group.

<a name="built-in-middleware"></a>
## Built-in Middleware

Import these from `arvel.http.middleware` (most are also on the top-level `arvel`).

<a name="authenticate"></a>
### Authenticate

`Authenticate(guard_name="web")` requires an authenticated user, resolving via the named [auth guard](../features/authentication.md). On success it sets `request.state.user`; with no user (or no auth wiring), it raises `UnauthenticatedException` (`401`).

```python
Authenticate("api")
```

For routes that work with or without a user, the auth package provides `OptionalAuthenticate` (in `arvel.auth.middleware`), which sets `request.state.user` when present but never returns a `401`.

<a name="throttle-rate-limiting"></a>
### Throttle (Rate Limiting)

`Throttle(max_attempts, *, decay_seconds=60, key=None, store=None)` rate-limits requests. By default it keys on the client IP; over the limit it raises `ThrottleException` (`429`) with a `Retry-After` header:

```python
Throttle(100, decay_seconds=60)
```

Pass a custom `key` callable to limit per user or per token, and a `store` to share counters across processes:

```python
from arvel.http.ratelimit import RedisStore

Throttle(100, decay_seconds=60, store=RedisStore(redis_client))
```

| Store | Use |
|---|---|
| `InMemoryStore` | Process-local. Fine for a single-process dev server. |
| `RedisStore(client, key_prefix="arvel:rl:")` | Shared across processes; needs a Redis client with `incr`/`expire`. |

> [!NOTE]
> When no `store` is passed, each `Throttle` instance creates its own `InMemoryStore`. For multi-process deployments, construct a shared store and pass it explicitly. The `X-RateLimit-Limit` / `X-RateLimit-Remaining` headers are added only when the handler returns a Starlette `Response`, not a plain dict.

<a name="verifycsrf"></a>
### VerifyCsrf

`VerifyCsrf(except_paths=None)` verifies a CSRF token on state-changing requests. It skips `GET`/`HEAD`/`OPTIONS` and any path listed in `except_paths`. It reads the expected token from the session key `_csrf_token` and the submitted token, in order, from the `X-CSRF-Token` header, the `X-XSRF-TOKEN` header (the alias Axios sends from the `XSRF-TOKEN` cookie), or the `_token` field of an `application/x-www-form-urlencoded` body. A mismatch raises a CSRF error — **HTTP 419**, code `CSRF_MISMATCH`.

> [!NOTE]
> Only urlencoded form bodies are inspected for `_token` — JSON and multipart (upload) bodies aren't buffered, so put the token in a header for those. The same `CsrfMismatchException` (419) backs both `VerifyCsrf` and the cookie-based `CsrfDoubleSubmitMiddleware`.

```python
VerifyCsrf(except_paths=["/api/webhooks/"])
```

> [!NOTE]
> `VerifyCsrf` only *checks* tokens; it doesn't generate them. It expects a token already present in the session, so it requires session middleware to be configured. Token-based APIs using bearer tokens typically don't need it.

<a name="signed"></a>
### Signed

`SignedMiddleware()` (from `arvel.http.middleware`) rejects requests whose [signed URL](routing.md#signed-urls) signature is missing or invalid, returning a `403`. Attach it to routes that should only be reachable via a signed link.

<a name="application-middleware"></a>
## Application Middleware

Application middleware operates at the ASGI layer and wraps the whole app rather than individual routes.

<a name="cors"></a>
### CORS

CORS is configured by adding the `Cors` middleware to the ASGI app (it extends Starlette's `CORSMiddleware`):

```python
from arvel.http.middleware import Cors

app.add_middleware(
    Cors,
    allowed_origins=["https://app.example.com"],
    allowed_methods=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
    allowed_headers=("Authorization", "Content-Type", "X-Requested-With"),
    allow_credentials=False,
    max_age=600,
)
```

> [!WARNING]
> `allow_credentials=True` together with a wildcard origin raises `ValueError`. When you need credentials, list explicit origins.

<a name="other-asgi-middleware"></a>
### Other ASGI Middleware

Arvel ships several ASGI middleware you can add to the stack, including `SecurityHeadersMiddleware` (HSTS, CSP, and friends) and `MethodSpoofMiddleware` (turns a `POST` with a `_method` field into `PUT`/`PATCH`/`DELETE`). The framework also installs request-scope, [context](../features/logging.md), deferred-task, and observability middleware automatically when the app boots.

<a name="generating-middleware"></a>
## Generating Middleware

Scaffold a route middleware with:

```bash
arvel make:middleware EnsureTenant
```
