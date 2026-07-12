# Request Lifecycle

Understanding the path a request takes — from the ASGI server to your handler and back — makes the
rest of the framework easier to reason about. This page traces that path. (For how the app *boots*,
see [Architecture Concepts](architecture.md#the-application-lifecycle).)

## Entry point

Every request enters through the ASGI application your server imports:

```python
# asgi.py
asgi_app = create_app().as_asgi()      # a real litestar.Litestar instance
```

By the time a request arrives, the app is fully booted: providers registered, routes compiled onto
Litestar, middleware stacks assembled. arvel's dynamic `Route.get(...)` definitions have been
adapted onto Litestar route handlers, so a request is matched by the same battle-tested router that
generates your OpenAPI.

## The middleware pipeline

A matched request runs through a **two-tier middleware pipeline** before it reaches your handler:

1. **Global middleware** — runs for every request. The defaults (in order) start the telemetry span, bind a request id into
   the log context, gate maintenance mode, validate host and body size, normalize input (trim
   strings, empty-string→null), and set the request locale.
2. **Group middleware** — runs for the route's group. The `web` group adds cookie encryption,
   sessions, shared view errors, and CSRF; the `api` group adds throttling.

Each middleware may inspect the request, short-circuit with a response, or pass control onward.
Ordering across tiers can be pinned when it matters (see [Middleware](middleware.md)).

Per request, arvel also resets the request-scoped context — the current request, the authenticated
user, and the active token are cleared at the pipeline boundary so nothing leaks between requests
that share an execution context.

## Route binding & the handler

Once the pipeline passes control through, arvel resolves the route's parameters — including
**implicit model binding**, where a `{post}` segment is loaded into a `Post` model — and calls your
handler. A handler is an `async` function; return a dict (arvel sends JSON), a `Response`, or a view
(arvel renders HTML). See [Routing](routing.md).

A deliberate detail: a missing bound model is **not** rendered as a 404 before the pipeline runs.
Doing so would let an unauthenticated client tell an existing id from a nonexistent one with zero
credentials — so the outcome is deferred until after auth/authorization have had their say.

## The response & termination

Your handler's return value is turned into a `Response`, which travels back out through the
pipeline (each middleware may decorate it). After the response is built, any **terminable**
middleware runs its `terminate` hook — session flushing, request logging — work that should happen
*after* the client has its answer.

## In summary

```
ASGI server
  → matched route
    → global middleware (request id, maintenance, host/size, normalize, locale)
      → group middleware (web: session/CSRF · api: throttle)
        → route binding (implicit model binding)
          → your handler → Response
        ← group middleware (decorate)
      ← global middleware
    ← terminate hooks (session flush, logging)
  → response to the client
```

The three subsystems doing the work inside this flow each get their own page — the
[service container](container.md), [service providers](providers.md), and
[facades](facades.md).
