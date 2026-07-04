# Middleware

Some logic doesn't belong in any one handler — it belongs *around* all of them: authentication,
sessions, CSRF protection, rate limiting, request logging. Middleware is where that lives. Each one
wraps the request, runs code on the way in and on the way out, and decides whether to pass control
deeper or stop short.

arvel composes them in three tiers per request — **global** (every request), then the route's
**group** (`web`/`api`), then any **route-specific** middleware — all on top of Litestar. This page
covers writing your own, the built-in set, and how routes pick up the right middleware.

!!! note "Needs the `[http]` extra"
    Middleware runs in the serve path — `uv add 'arvel[http]'` (Litestar).

## Writing middleware

Subclass `Middleware` and implement `handle(request, call_next)`. Call `call_next` to continue
the pipeline; return a `Response` instead to short-circuit:

```python
from arvel.http.middleware import Middleware

class MeasureTime(Middleware):
    async def handle(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)        # run the rest of the pipeline + handler
        log.info("request", path=request.path(), ms=(time.perf_counter() - start) * 1000)
        return response
```

The pattern is an onion: code before `call_next` runs on the way in, code after runs on the way
out, and short-circuiting (returning without calling `call_next`) skips everything inward.

## Groups: `web` vs `api`

Routes belong to a middleware **group**. arvel ships two:

| Group | Default middleware | For |
|-------|--------------------|-----|
| `web` | `StartSession`, `ShareErrorsFromSession`, `ValidateCsrfToken` | browser pages (cookies, sessions, CSRF, flashed errors) |
| `api` | `ThrottleRequests` | stateless JSON APIs (rate-limited) |

Before any group runs, a handful of **global** middleware run on *every* request: the maintenance
gate (`503` while the app is down), `ValidatePostSize` (`413` on an over-large body), and
`ValidateHost` (`400` on an untrusted `Host`). You don't wire these up — they're on by default.

**Add your own global middleware** in `bootstrap/middlewares.py` (the list the fluent
`with_middlewares(...)` loads) — they run on every request, after the built-in global gate:

```python
# bootstrap/middlewares.py
from arvel.http.middleware import AuthenticateMiddleware

middlewares = [AuthenticateMiddleware]   # resolves the request user into `current_user`
```

Populate the group defaults at boot and tweak them:

```python
kernel.use_default_groups()                        # web + api with their defaults
kernel.append_to_group("web", EnsureTeamSelected)  # add to a group
kernel.prepend_to_group("api", TrustProxies)       # run first
kernel.middleware_group("admin", [Authenticate, EnsureAdmin])   # a new named group
```

The `web`/`api` defaults are populated automatically when the app is served, so a route assigned
to a group gets its middleware with no extra wiring.

## Assigning middleware to routes

Attach a group, or specific middleware, when you define routes. Assign a single route directly,
or wrap a block in a [group](routing.md#groups):

```python
Route.get("/dashboard", show, group="web")         # run the web group (session + CSRF)

with router.group(group="web", middleware=[Authenticate]):
    router.get("/account", account)                # web group + Authenticate
    router.get("/billing", billing).middleware(EnsureSubscribed)   # + one more, this route only
```

Per request the middleware run **outermost-first** in three tiers: **global → group → route**.
Nested `group(...)` blocks compose (outer middleware then inner), and everything is restored when
the block exits, so sibling routes aren't affected.

## Aliases

Give a middleware a short name and reference it by that name in groups or routes:

```python
kernel.alias({"auth": Authenticate, "throttle": ThrottleRequests})
```

## The built-in middleware

Global (every request, on by default):

- **`PreventRequestsDuringMaintenance`** — returns `503` while the app is in maintenance mode.
- **`ValidatePostSize`** — rejects a body larger than `config('app.max_request_size')` (default
  10 MiB) with `413`, before the handler runs.
- **`ValidateHost`** — `400` when the `Host` isn't in `config('app.trusted_hosts')` (a no-op until
  you configure it).
- **`MethodOverride`** — HTML form method-spoofing (Laravel `@method`): a `POST` whose form body
  (`application/x-www-form-urlencoded` or `multipart/form-data`) carries `_method=PUT|PATCH|DELETE` is
  routed as that verb, so a `<form method="post">` can reach a PUT/PATCH/DELETE route. Runs at the ASGI
  layer before routing; emit the field with `{{ method_field('PUT') }}`.

Group / opt-in:

- **`ThrottleRequests(max_attempts, decay_seconds)`** — rate-limit per client; over the limit
  raises a `429`. Keyed by `request.ip()` (the first trusted `X-Forwarded-For` hop, else the socket
  peer).
- **`StartSession`** — attaches a `request.session` dict loaded from (and saved back to) the
  session store, keyed by the `session` cookie. The store is an in-process dict by default (lost
  on restart, not shared across workers); set `session.driver = "redis"` in config (the app's own
  bound `Cache` service — the same Redis/Valkey connection already configured for caching, not a
  second one) to persist sessions across restarts and share them across every worker/host —
  `HttpKernel.use_default_groups()` wires this automatically, no route/middleware code needed.
- **`ShareErrorsFromSession`** — exposes the session's flashed validation errors to views as
  `errors` (see [Validation](validation.md)).
- **`ValidateCsrfToken`** — seeds a per-session CSRF token, then requires state-changing requests
  to send a matching one — via the `_token` form field (`{{ csrf_field() }}` in a form) or an
  `X-CSRF-TOKEN` / `X-XSRF-TOKEN` header (read `{{ csrf_token() }}` into a meta tag for JS). A
  missing/mismatched token is a `419`; safe methods (GET/HEAD/OPTIONS) are exempt. See
  [Views](views.md) for the template helpers.
- **`RequestContext`**, **`Locale`**, **`Authenticate`** — bind a request id, set the locale
  from `Accept-Language`, and resolve the current user.

## CSRF from a SPA or mobile app

Which path you take depends on **how the client authenticates**:

**Mobile apps & decoupled / cross-origin frontends → use the API (no CSRF).** Put these routes in
the `api` group, which is stateless (no session, no `ValidateCsrfToken`) and authenticates with a
**bearer token** (`Authorization: Bearer <token>`). CSRF is a cookie-session attack — it does not
apply to token auth, because a browser never auto-attaches a bearer token to a forged request. This
is the recommended path for mobile and any frontend you don't serve from the same origin.

```http
POST /api/items            # api group — throttled, token-authed, CSRF does not apply
Authorization: Bearer 1|abc...
```

See [API tokens](auth/api-tokens.md) for issuing tokens.

**Decoupled SPA using the session cookie (the `web` group) → the `XSRF-TOKEN` cookie flow.** The
session-id cookie is `HttpOnly` (JS can't read it), so the web group also sets a **readable
`XSRF-TOKEN` cookie** holding the token — exactly Laravel/Sanctum. The SPA never needs a
server-rendered page:

1. On startup, make a `GET` to any web-group route (add a no-op `Route.get("/csrf-cookie", …)` for
   this) — the response carries `Set-Cookie: XSRF-TOKEN=…`.
2. Read that cookie in JS and echo it back as the `X-XSRF-TOKEN` header on every state-changing
   request. **axios does this automatically** (it reads the `XSRF-TOKEN` cookie by default):

```js
await axios.get("/csrf-cookie");           // primes the XSRF-TOKEN cookie
await axios.post("/profile", data);        // axios auto-sends X-XSRF-TOKEN — no extra wiring
```

With `fetch`, read the cookie yourself and set the header:

```js
const xsrf = document.cookie.match(/XSRF-TOKEN=([^;]+)/)[1];
await fetch("/profile", { method: "POST", headers: { "X-XSRF-TOKEN": xsrf } });
```

The cookie flow is **same-site only**: the cookies are `SameSite=Lax` (and the session cookie uses the
`__Host-` prefix), so the SPA and API must share a registrable domain — e.g. the SPA on
`app.example.com` and the API on `example.com` or `api.example.com`. A truly cross-**site** browser
SPA isn't supported by these cookie attributes; for that, authenticate it as an API client with a
**bearer token** (the first option above) instead of cookies.

**Server-rendered pages** (arvel renders the HTML) can skip the cookie and read the token from a meta
tag or use a form field directly:

```html
<meta name="csrf-token" content="{{ csrf_token() }}">   <!-- for JS -->
<form method="post">{{ csrf_field() }} …</form>          <!-- hidden _token field -->
```

Both `X-CSRF-TOKEN` and `X-XSRF-TOKEN` headers (and the `_token` body field) are accepted; a
missing/mismatched token is a `419`.

## Common mistakes & gotchas

- **Forgetting to return the response.** `handle` must return what `call_next` gave you (or your
  own `Response`). Returning `None` drops the response.
- **Heavy work on every request.** Middleware runs for *every* matching request — keep it lean;
  push slow work to the queue.
- **Throttle/session state in tests.** Both use a process-shared store; in tests, use a unique
  limiter `name=` or a fresh store so cases don't interfere.
- **CSRF on an API.** The `api` group is stateless — don't add `ValidateCsrfToken` there; use a
  token guard for API auth instead.

## How it works

The `HttpKernel` composes, per request, `[*global_middleware, *groups[group], *route_middleware]`,
resolving any alias strings, and runs them as a chain of responsibility: each middleware's `handle` receives
a `call_next` that invokes the next one, ending at your handler. The whole pipeline sits on a
real `litestar.Litestar` app, so routing and OpenAPI come from Litestar while the two-tier
group model gives you the familiar web/api split.

## See also

- [Routing](routing.md) — assigning routes to groups.
- [Authentication](auth/index.md) — the auth middleware + guards.
