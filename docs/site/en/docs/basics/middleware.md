# Middleware

Middleware in Arvel is pure ASGI: a callable that receives the next app and eventually forwards `scope`, `receive`, and `send`. There is no `BaseHTTPMiddleware` magic—just explicit chains that are easy to reason about and friendly to async code. The framework layers two ideas on top: **alias resolution** (string names to classes at boot) and **ordering** (global stack priorities plus per-route wrapping).

## The `Middleware` protocol

Implementations store the inner app on `self.app` and implement `async def __call__(self, scope, receive, send)`. That matches how Starlette composes ASGI apps and keeps typing straightforward via the `Middleware` protocol.

```python
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send


class AddRequestId:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            # ... mutate scope or stash state ...
        await self.app(scope, receive, send)
```

## Terminable middleware

Some middleware needs to run **after** the response finishes—think session persistence or metrics flush. The `TerminableMiddleware` protocol extends `Middleware` with `async def terminate(self) -> None`. The HTTP kernel documents a last-in-first-out terminate order alongside global registration; implement it when your middleware owns resources that outlive the response body.

## `MiddlewareStack`: aliases and groups

Boot-time config maps short names to import paths (`HttpSettings.middleware_aliases`) and optional bundles (`middleware_groups`). `MiddlewareStack.expand` flattens group names recursively and detects circular group definitions. `resolve` imports each concrete class once and returns the types in order.

This is how route-level `middleware=["auth", "throttle"]` strings become real classes without hard-coding imports in every route file.

```python
from arvel.http import MiddlewareStack

stack = MiddlewareStack(
    aliases={
        "auth": "myapp.http.middleware.AuthMiddleware",
        "throttle": "myapp.http.middleware.ThrottleMiddleware",
    },
    groups={"api": ["auth", "throttle"]},
)

classes = stack.resolve(stack.expand(["api"]))
```

Unknown aliases raise `MiddlewareResolutionError` with the name that failed—fix the config rather than debugging a silent skip.

## Global middleware and `HttpKernel`

`HttpKernel` owns the **outer** stack around the FastAPI app. Register classes with `add_global_middleware(cls, priority=50)`. Lower priority numbers run **earlier** on the request path (outer layers of the onion). On `mount`, the kernel applies middleware in reverse sorted order so the priority semantics match the docstring: lowest number ends up outermost.

Your `HttpSettings.global_middleware` list pairs alias names with priorities; the HTTP service provider resolves aliases and registers them on the kernel.

## Request-scoped containers

`RequestScopeMiddleware` (often registered globally) enters a request scope on the application container and stores the child container at `scope["state"]["container"]`. That is what powers controller DI and `Inject(...)`—without it, resolving services from the container inside a request will fail fast with a helpful error.

## Per-route middleware

After routes are included on the app, the HTTP provider wraps individual route ASGI apps when a `RouteEntry` lists middleware. Effective middleware is computed by expanding groups, applying `without_middleware` exclusions, then resolving. This keeps global concerns (logging, errors) separate from route-specific gates (auth on one POST, public GET on another).

## Configuration recap

`HttpSettings` (env prefix `HTTP_`) carries:

- `middleware_aliases`: name → `module.Class` path
- `middleware_groups`: name → list of alias names
- `global_middleware`: list of `(alias, priority)` tuples

Tune those values rather than editing generated middleware lists in multiple places.
