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

## Pinning relative order with `middleware_priority`

Insertion order (global → group → route) is usually enough, but sometimes two middleware need a
fixed relative order *regardless* of which tier put them on the stack — e.g. a session must always
start before anything that reads it, even if a route attaches that "anything" directly. Set
`kernel.middleware_priority` to a list of middleware **classes** in the order they must run:

```python
kernel.middleware_priority = [EncryptCookies, StartSession, ValidateCsrfToken]
```

Assembled for each request, the full stack is stably re-sorted: any middleware named in the list
runs in that relative order no matter where it was inserted; everything else keeps its original
relative position. Leave it empty (the default) for plain insertion order — no behavior change.

## Aliases

Give a middleware a short name and reference it by that name in groups or routes:

```python
kernel.alias({"auth": Authenticate, "throttle": ThrottleRequests})
```

## Rate limiting

`ThrottleRequests` has two modes. The plain one (used by the `api` group's default) takes
`max_attempts`/`decay_seconds` directly and returns a `429` over the limit — carrying the same
`Retry-After` + `X-RateLimit-Limit`/`Remaining`/`Reset` headers the named mode does (and setting the
limit headers on allowed responses too). See the built-in middleware list below.

The other is **named limiters**: define the rule once, reuse it from any route via
`throttle:<name>`. Register a limiter on the app's `limiter` (the `RateLimiter` facade) — typically
in a service provider's `boot()`:

```python
from arvel.support.facades import RateLimiter
from arvel.http.rate_limiter import Limit

class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        # 60 requests/minute, segmented by authenticated user id (else client IP)
        RateLimiter.for_("api", lambda request: Limit.per_minute(60))

        # multiple limits (both enforced), explicitly segmented
        RateLimiter.for_(
            "uploads",
            lambda request: [Limit.per_minute(10).by(request.ip()), Limit.per_day(200)],
        )

        # unlimited for this request — return None from the resolver
        RateLimiter.for_("webhooks", lambda request: None)
```

Then attach it to a route or group with the `throttle:<name>` string:

```python
Route.get("/reports", show).middleware("throttle:api")

with router.group(group="api", middleware=["throttle:uploads"]):
    router.post("/uploads", store)
```

A request over any of the limiter's `Limit`s gets a `429` with `Retry-After`,
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers; a request under the
limit gets `X-RateLimit-Limit`/`X-RateLimit-Remaining` too. Build your own `429` instead of the default JSON
one with `.response(...)`:

```python
Limit.per_minute(5).response(lambda request: {"message": "Slow down."})
```

**Segmenting.** A `Limit` with no explicit `.by(key)` is keyed by the authenticated user's id, else
the client IP — call `.by(...)` yourself to segment differently (per tenant,
per API key, …).

**Window.** Counting is fixed-window (a cache TTL arms on the first hit in a window) — the same
technique the plain `ThrottleRequests` mode and the own limiter use. A burst can straddle two
windows (e.g. a client could squeeze in ~2x the limit right at a window boundary); it's not a
sliding-window limiter. Good enough for the vast majority of rate-limiting needs; reach for a
dedicated rate-limiting proxy/service if you need a hard sliding-window guarantee.

**Direct use.** The low-level verbs (`hit`, `too_many_attempts`, `remaining`, `available_in`,
`clear`, and the combined `attempt`) work with any caller-chosen key — no registered limiter
required — e.g. for a login-lockout check inside a handler:

```python
if await RateLimiter.too_many_attempts(f"login:{email}", 5):
    abort(429, f"Try again in {await RateLimiter.available_in(f'login:{email}')}s")
```

## The built-in middleware

Global (every request, on by default):

- **`PreventRequestsDuringMaintenance`** — returns `503` while the app is in maintenance mode.
- **`ValidatePostSize`** — rejects a body larger than `config('app.max_request_size')` (default
  10 MiB) with `413`, before the handler runs.
- **`ValidateHost`** — `400` when the `Host` isn't in `config('app.trusted_hosts')` (a no-op until
  you configure it).
- **`TrimStrings`** — strips leading/trailing whitespace from every string in the parsed input,
  recursively; `password`, `password_confirmation`, and `current_password` keys are left untouched
  (a password reaches validation exactly as typed).
- **`ConvertEmptyStringsToNull`** — turns every `""` into `None`, recursively. This flips
  validation outcomes the way you'd want: a `nullable` field submitted empty now passes, a
  `required` one now fails. Both normalizers feed the single input pipeline, so `validate()` and
  `request.input(...)` see the same cleaned values.
- **`MethodOverride`** — HTML form method-spoofing: a `POST` whose form body
  (`application/x-www-form-urlencoded` or `multipart/form-data`) carries `_method=PUT|PATCH|DELETE` is
  routed as that verb, so a `<form method="post">` can reach a PUT/PATCH/DELETE route. Runs at the ASGI
  layer before routing; emit the field with `{{ method_field('PUT') }}`.

Group / opt-in:

- **`EncryptCookies`** — first in the `web` group: encrypts every outgoing cookie value with the
  app key and decrypts them on the way in, so a client never sees (or can tamper with) a raw
  session id. A tampered or undecryptable cookie reads as absent — a fresh session, not an error.
  The `XSRF-TOKEN` cookie is excepted by design: it's the double-submit CSRF token a SPA must read
  in JavaScript, not a secret. Cookie encryption is only active when `APP_KEY` is set —
  `arvel new` generates one, so scaffolded apps have it from the first request.
- **`ThrottleRequests(max_attempts, decay_seconds)`** — rate-limit per client; over the limit
  raises a `429`. Keyed by `request.ip()` (the first trusted `X-Forwarded-For` hop, else the socket
  peer). The `throttle:<name>` string form runs a different, header-carrying mode instead — see
  [Rate limiting](#rate-limiting) above.
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
  `X-CSRF-TOKEN` / `X-XSRF-TOKEN` header (read `{{ csrf_token() }}` into a meta tag for JS). It
  also verifies **provenance**: a request carrying an `Origin` header (or, failing that, a
  `Referer`) must come from the request's own host or a `session.trusted_origins` entry — a
  cross-site request is a `419` even if its token is somehow valid. Clients that send neither
  header (curl, native apps) are judged by the token alone. A missing/mismatched token is a
  `419`; safe methods (GET/HEAD/OPTIONS) are exempt. Trusted origins are bare hosts
  (`partner.example`, any scheme/port) or full origins matched exactly as the browser sends
  them — write `https://partner.example`, not `https://partner.example:443` or a trailing
  slash, since browsers omit default ports. See
  [Views](views.md) for the template helpers.
- **`RequestContext`**, **`Locale`**, **`Authenticate`** — bind a request id, set the locale
  from `Accept-Language`, and resolve the current user.

### Excepting routes from CSRF

A route a third party posts to with no session (a webhook) can't carry a CSRF token — exempt it
by URI glob pattern, either in config or on a subclass:

```python
# config/session.py
"csrf_except": ["webhooks/*"],
```

```python
from arvel.http.middleware import ValidateCsrfToken

class AppCsrf(ValidateCsrfToken):
    except_ = ["webhooks/*", "health"]   # merged with config('session.csrf_except'), not replaced
```

Swap it into the web group in place of the default:

```python
kernel.use_default_groups()
kernel.groups["web"] = [
    AppCsrf if mw is ValidateCsrfToken else mw for mw in kernel.groups["web"]
]
```

Every other state-changing route on the exempted middleware still gets a `419` without a valid
token — only the listed patterns skip the check.

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

See [API Tokens](auth/api-tokens.md) for issuing tokens.

**Decoupled SPA using the session cookie (the `web` group) → the `XSRF-TOKEN` cookie flow.** The
session-id cookie is `HttpOnly` (JS can't read it), so the web group also sets a **readable
`XSRF-TOKEN` cookie** holding the token. The SPA never needs a
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
