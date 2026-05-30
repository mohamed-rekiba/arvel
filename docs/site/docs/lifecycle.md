# Request Lifecycle

Every HTTP request to an Arvel app travels through the same chain of layers. Knowing the path helps you pick the right extension point and understand what runs when.

## Lifecycle overview

### First things first

The entry point for all requests is your **ASGI application factory**, typically `create_app` in your `app.py`:

```python
from arvel import ASGIApp, Application

_app = Application.configure(".").with_environment_from_env().create()


def create_app() -> ASGIApp:
    return _app.into_asgi()
```

`Application.configure(...).create()` builds the `Application` object — but does **not** boot it yet. Boot is deferred until `into_asgi()` is called.

`into_asgi()`:

1. Resolves and registers all `ServiceProvider`s.
2. Calls `register()` on each provider (synchronous, no I/O).
3. Wires the boot phase into the ASGI lifespan event so async `boot()` calls run on app startup.
4. Mounts all `Route` decorators that have been collected into the singleton `Router`.
5. Returns a Starlette-compatible ASGI callable.

When Uvicorn starts your app, it sends a `lifespan.startup` event. Arvel handles that event by:

6. Awaiting each provider's `boot()` method, in registration order.
7. Marking the app as booted.

### HTTP request → response

Once your application is booted and Uvicorn receives a real HTTP request:

```
Client request
    ↓
Uvicorn / ASGI server
    ↓
Starlette base application
    ↓
Starlette-level middleware  (CORS, request logging, anything app-wide)
    ↓
FastAPI router  (URL match, FastAPI dependency resolution, OpenAPI binding)
    ↓
Arvel route-level middleware pipeline  (Authenticate, Throttle, CSRF, custom guards)
    ↓
Your handler  (async function or controller)
    ↓
Response  (typed return value → JSON / HTML / streaming)
    ↓
Back up through middleware (in reverse order)
    ↓
Client
```

Arvel has **two tiers** of middleware:

| Tier | Where it runs | When to use it |
|---|---|---|
| **App-level (Starlette)** | Wraps every request before FastAPI sees it | CORS, request ID, structured access logs, anything that must wrap every request |
| **Route-level (Arvel pipeline)** | Inside the matched route, before the handler | Authentication, throttling, CSRF, authorization, anything per-route |

The two tiers exist because Starlette middleware can't see the matched route (the URL hasn't been resolved yet), so it's the wrong place for per-route concerns.

## Focus on service providers

The most important act during the boot lifecycle is **loading service providers**. Providers are the central place to configure your application. They register bindings into the container, attach event listeners, register middleware, and load routes.

Service providers expose two phases:

| Method | When it runs | What it can do |
|---|---|---|
| `register()` | During `into_asgi()`, synchronously | Bind classes, factories, and singletons. **Never** call other services here (they might not be registered yet). |
| `boot()` | During ASGI lifespan startup, asynchronously | Resolve other services. Run migrations. Attach event listeners. Hit the network if you must. |

The order is critical: every `register()` runs before any `boot()`. That's how you avoid the chicken-and-egg problem of one provider depending on another.

See [Service Providers](providers.md) for the full guide.

## Why this matters

Knowing the lifecycle helps you choose the right hook:

- Need to register a binding? → Provider `register()`.
- Need to set up I/O state? → Provider `boot()`.
- Need to wrap every request app-wide? → App-level middleware.
- Need to wrap a subset of routes? → Route-level middleware via `Route.group(middleware=...)`.
- Need to validate request input? → A `FormRequest` subclass.
- Need to transform the response shape? → A `JsonResource` subclass.
- Need a side effect after a model save? → Model lifecycle hook (`@on_created`, observer).

The lifecycle is the map. Once you know it, the rest of the framework falls into place.

## Where to next?

- [Service Container](container.md) — how DI actually works.
- [Service Providers](providers.md) — register vs boot, common patterns.
- [Facades](facades.md) — how `Route`, `Cache`, `DB` resolve under the hood.
- [Middleware](middleware.md) — the request pipeline in detail.
