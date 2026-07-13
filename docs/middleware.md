# Middleware

Some logic doesn't belong in any one handler — it belongs *around* all of them: authentication,
sessions, CSRF protection, rate limiting, request logging. Middleware is where that lives. Each one
wraps the request, runs code on the way in and on the way out, and decides whether to pass control
deeper or stop short.

!!! note "Needs the `[http]` extra"
    Middleware runs in the serve path — `uv add 'arvel[http]'` (Litestar).

## Defining middleware

Subclass `Middleware` and implement `handle(request, call_next)`. Call `call_next` to continue the
pipeline; return a `Response` instead to short-circuit:

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

## Registering middleware

Per request the middleware run **outermost-first** in three tiers: **global → group → route**.

### Global middleware

To run a middleware on every HTTP request, list it in `bootstrap/middlewares.py` (the list the
fluent `with_middlewares(...)` loads) — it runs after the built-in global gate:

```python
# bootstrap/middlewares.py
from arvel.http.middleware import AuthenticateMiddleware

middlewares = [AuthenticateMiddleware]   # resolves the request user into `current_user`
```

### Assigning middleware to routes

Attach a group, or specific middleware, when you define routes — a single route directly, or a
whole [group block](routing.md#route-groups):

```python
Route.get("/dashboard", show, group="web")         # run the web group (session + CSRF)

with router.group(group="web", middleware=[Authenticate]):
    router.get("/account", account)                # web group + Authenticate
    router.get("/billing", billing).middleware(EnsureSubscribed)   # + one more, this route only
```

### Middleware groups

Routes belong to a middleware **group**. arvel ships two:

| Group | Default middleware | For |
|-------|--------------------|-----|
| `web` | `StartSession`, `ShareErrorsFromSession`, `ValidateCsrfToken` | browser pages (cookies, sessions, CSRF, flashed errors) |
| `api` | `ThrottleRequests` | stateless JSON APIs (rate-limited) |

Populate the defaults at boot and tweak them, or define your own named group:

```python
kernel.use_default_groups()                        # web + api with their defaults
kernel.append_to_group("web", EnsureTeamSelected)  # add to a group
kernel.prepend_to_group("api", TrustProxies)       # run first
kernel.middleware_group("admin", [Authenticate, EnsureAdmin])   # a new named group
```

### Sorting middleware

Insertion order (global → group → route) is usually enough, but sometimes two middleware need a
fixed relative order *regardless* of which tier put them on the stack — e.g. a session must start
before anything that reads it. Set `kernel.middleware_priority` to a list of middleware **classes**
in the order they must run:

```python
kernel.middleware_priority = [EncryptCookies, StartSession, ValidateCsrfToken]
```

The full stack is stably re-sorted: any middleware named in the list runs in that relative order no
matter where it was inserted; everything else keeps its position. Leave it empty for plain
insertion order.

## Middleware parameters

Middleware can receive parameters. Register a short **alias** for a class, then reference it by name
— and, for parameterized middleware, pass an argument after a colon:

```python
kernel.alias({"auth": Authenticate, "throttle": ThrottleRequests})
```

```python
Route.get("/reports", show).middleware("throttle:api")   # the "api" named rate limiter
```

The `throttle:<name>` form is the built-in example — it selects a named rate limiter. See
[Rate Limiting](rate-limiting.md) for defining limiters.

## Terminable middleware

Sometimes middleware needs to do work once the response is built — writing a session, flushing a log.
Implement `terminate(request, response)` in addition to `handle`; the kernel runs it after the response
is built but **before** it's returned to the ASGI server, on the same instance (so state set in
`handle` is visible in `terminate`). Because it runs before delivery it adds to request latency — keep
it light and push anything slow onto the queue:

```python
class StoreVisit(Middleware):
    async def handle(self, request, call_next):
        self.started = time.time()
        return await call_next(request)

    async def terminate(self, request, response):
        await record_visit(request.path(), took=time.time() - self.started)
```

## Available middleware

Global middleware run on *every* request and are on by default — you don't wire them up:

- **`PreventRequestsDuringMaintenance`** — `503` while the app is in maintenance mode.
- **`ValidatePostSize`** — `413` on a body larger than `config('app.max_request_size')` (default 10 MiB).
- **`ValidateHost`** — `400` when the `Host` isn't in `config('app.trusted_hosts')` (a no-op until configured).
- **`TrimStrings`** — strips leading/trailing whitespace from every string in the parsed input;
  `password`/`password_confirmation`/`current_password` are left untouched.
- **`ConvertEmptyStringsToNull`** — turns every `""` into `None`, so a `nullable` field submitted
  empty passes and a `required` one fails.
- **`MethodOverride`** — HTML form [method spoofing](routing.md#form-method-spoofing).

Group / opt-in middleware:

- **`EncryptCookies`** — encrypts every outgoing cookie with the app key (active when `APP_KEY` is
  set; the `XSRF-TOKEN` cookie is excepted by design).
- **`StartSession`** — attaches the `request.session` dict from the session store (see [Session](session.md)).
- **`ShareErrorsFromSession`** — exposes flashed validation `errors` to views (see [Validation](validation.md)).
- **`ValidateCsrfToken`** — the web group's CSRF guard (see [CSRF Protection](csrf.md)).
- **`ThrottleRequests`** — the rate limiter (see [Rate Limiting](rate-limiting.md)).
- **`RequestContext`**, **`Locale`**, **`Authenticate`** — bind a request id, resolve the request
  locale, and resolve the current user. `Locale` picks the locale by precedence: an explicit switch
  (`?lang=` / a `locale` cookie), then the signed-in user's saved preference, then `Accept-Language`
  (see [Localization](localization.md)).

## Common mistakes & gotchas

- **Forgetting to return the response.** `handle` must return what `call_next` gave you (or your own
  `Response`). Returning `None` drops the response.
- **Heavy work on every request.** Middleware runs for *every* matching request — keep it lean; push
  slow work to the queue.
- **CSRF on an API.** The `api` group is stateless — don't add `ValidateCsrfToken` there; use a token
  guard for API auth instead.

## See also

- [Routing](routing.md) — assigning routes to groups.
- [CSRF Protection](csrf.md) — the `web` group's CSRF token flow, SPA cookies, exemptions.
- [Rate Limiting](rate-limiting.md) — named limiters and `throttle:<name>`.
- [Authentication](auth/authentication.md) — the auth middleware + guards.
