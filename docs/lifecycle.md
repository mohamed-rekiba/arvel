# Request Lifecycle

When using any tool in the "real world," you feel more confident if you understand how that tool
works. Application development is no different. When you understand how your framework functions, you
feel more comfortable and confident using it. This page traces the path a request takes — from the
ASGI server to your handler and back.

## First steps

Every request enters through the ASGI application your server imports:

```python
# asgi.py
asgi_app = create_app().as_asgi()      # a real litestar.Litestar instance
```

By the time a request arrives, the app is fully booted: providers registered, routes compiled onto
Litestar, middleware stacks assembled. arvel's dynamic `Route.get(...)` definitions have been adapted
onto Litestar route handlers, so a request is matched by the same battle-tested router that generates
your OpenAPI schema.

## The kernels & middleware

A matched request runs through a **two-tier middleware pipeline** before it reaches your handler —
the arvel equivalent of the HTTP kernel:

1. **Global middleware** — runs for every request. The defaults (in order) start the telemetry span,
   bind a request id into the log context, gate maintenance mode, validate host and body size,
   normalize input (trim strings, empty-string→null), and set the request locale.
2. **Group middleware** — runs for the route's group. The `web` group adds cookie encryption, sessions,
   shared view errors, and CSRF; the `api` group adds throttling.

Each middleware may inspect the request, short-circuit with a response, or pass control onward.
Ordering across tiers can be pinned when it matters (see [Middleware](middleware.md)). Per request,
arvel also resets the request-scoped context — the current request, authenticated user, and active
token are cleared at the pipeline boundary so nothing leaks between requests.

## Service providers

The most important part of booting is loading **service providers**. They register every service the
framework and your app need — the database, queue, view, and validation subsystems are all bootstrapped
by a provider. The application iterates its providers, calling each one's `register` (bindings) and
then `boot` (wiring), and only then begins serving requests. This is the single most important concept
to grasp; see [Service Providers](providers.md).

## Routing

Once the pipeline passes control through, arvel resolves the route's parameters — including **implicit
model binding**, where a `{post}` segment is loaded into a `Post` model — and calls your handler. A
handler is an `async` function; return a dict (arvel sends JSON), a `Response`, or a view (arvel
renders HTML). See [Routing](routing.md) and [Responses](responses.md).

A deliberate detail: a missing bound model is **not** rendered as a 404 before the pipeline runs.
Doing so would let an unauthenticated client tell an existing id from a nonexistent one with zero
credentials — so the outcome is deferred until after auth/authorization have had their say.

## Finishing up

Your handler's return value is turned into a `Response`, which travels back out through the pipeline
(each middleware may decorate it). After the response is built, any **terminable** middleware runs its
`terminate` hook — session flushing, request logging — work that should happen *after* the client has
its answer.

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

## Focus on service providers

Service providers are the true key to bootstrapping an arvel application. The application is created,
the providers are registered and booted, and the request is handed to the booted application. It's
that simple! Having a firm grasp of how an arvel application is built and bootstrapped via service
providers is very valuable — the three subsystems doing the work each get their own page: the
[service container](container.md), [service providers](providers.md), and [facades](facades.md).
