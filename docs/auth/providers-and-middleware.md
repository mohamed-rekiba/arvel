# Wiring It Up: Providers & Middleware

The rest of this section gave you the *pieces* — guards, the user provider, gates, policies. This
page is about **assembly**: the two questions every app has to answer.

1. **Where do auth services get registered?** → in a **service provider** (`register()` binds them,
   `boot()` defines gates/policies).
2. **How does each request learn who its user is, and how do you protect routes?** → with
   **middleware**.

Get these two right and everything else in this section just works.

## What arvel already registers

The framework's `AuthServiceProvider` binds the core services into the container for you:

| Binding | What it is |
|---|---|
| `auth` | `AuthManager` — the session |
| `gate` | `Gate` — ability/policy checks |
| `guard` | `GuardManager` — the guard drivers |
| `auth.user_provider` | `UserProvider` over `DbIdentityStore` (from your `auth.user_model` / `trusted_email_providers` / `jit` config) |

So `app.make("gate")`, `app.make("guard")`, etc. are available out of the box. You add an
**app-level** `AuthServiceProvider` for the things only your app knows: the request's *user resolver*,
and your gates/policies.

## A service provider for your app

`register()` binds services; `boot()` runs after everything is registered, which is where you define
abilities and policies:

```python
from arvel.kernel.service_provider import ServiceProvider
from arvel.auth.tokens import TokenGuard

class AuthServiceProvider(ServiceProvider):
    def register(self) -> None:
        # How a request resolves to a user (see "AuthenticateMiddleware" below).
        async def resolve_user(request):
            user_id = await TokenGuard().user_id(request)      # or read it from the session
            return await User.find(user_id) if user_id is not None else None

        self.app.singleton("user_resolver", lambda app: resolve_user)

    def boot(self) -> None:
        gate = self.app.make("gate")
        gate.define("settings.manage", lambda user: user.has_role("admin"))
        gate.policy(Post, PostPolicy())
        gate.before(lambda user, ability: True if user.has_role("super-admin") else None)
```

## Establishing the user per request

`AuthenticateMiddleware` is what makes `request.user()` / `current_user` work: on every request it
calls your **`user_resolver`** binding, sets the result as the request's user, and clears it
afterwards. Add it to a middleware group:

```python
from arvel.http.middleware import AuthenticateMiddleware

kernel.append_to_group("web", AuthenticateMiddleware)
```

!!! warning "It needs a `user_resolver`"
    `AuthenticateMiddleware` resolves through the `user_resolver` binding. If you don't bind one,
    `current_user` stays `None` and every request looks like a guest. Bind it in your service
    provider (above) before relying on the middleware.

Note what this middleware does and doesn't do: it **populates** the user — it does **not** reject
guests. Requiring authentication is a separate step (next).

## Protecting routes

arvel ships a small set of route-protection middleware in `arvel.auth.middleware`. Each *enforces*
auth (whereas `AuthenticateMiddleware` only *populates* the user), aborting with the right status —
rendered content-negotiated by the kernel (JSON for APIs, redirect-back for web):

| Middleware | Alias | Effect |
|---|---|---|
| `Authenticate` | `auth` | **401** if not logged in |
| `RequireGuest` | `guest` | **403** if *already* logged in (login/register pages) |
| `EnsureEmailVerified` | `verified` | **401** guest · **403** if `email_verified_at` is unset |
| `Authorize("ability")` | — | **401** guest · **403** if the [Gate](authorization.md) denies the ability |

Register the parameter-less aliases once on the kernel, then reference them by name:

```python
from arvel.auth.middleware import Authorize, default_aliases

kernel.alias(default_aliases())          # {"auth": Authenticate, "guest": RequireGuest, "verified": EnsureEmailVerified}

# protect a whole group…
kernel.append_to_group("web", "auth")

# …or a single route (the `middleware=` arg of add_route):
kernel.add_route(["GET"], "/dashboard", dashboard, group="web", middleware=["auth"])
kernel.add_route(["GET"], "/billing",   billing,   group="web", middleware=["auth", "verified"])
```

`Authorize` is **parametrised** — it's a factory that returns a middleware *class* (the kernel
instantiates route middleware), so pass the ability per route:

```python
kernel.add_route(["PUT"], "/posts/{post}", update_post, middleware=["auth", Authorize("posts.update")])
```

These middleware read the user from `current_user`, so an earlier `AuthenticateMiddleware` must have
populated it (put it in the group ahead of them). Need bespoke behaviour — e.g. a *web* `auth` that
redirects to `/login` instead of returning 401? Subclass `Authenticate` and alias your version.

!!! tip "Catch typo'd abilities at boot"
    `Authorize("posts.updte")` (typo) fails closed — it just 403s every request, silently. To surface
    the mistake at startup instead, call `assert_abilities_defined(gate, middlewares)` in your
    provider's `boot()` with the route middleware you registered: it raises if any `Authorize(ability)`
    names an ability the [Gate](authorization.md) hasn't `define`-d. It's opt-in and checks only named
    (`Gate.define`) abilities — deny-by-default is unchanged; this only makes the typo loud.

    ```python
    from arvel.auth.middleware import assert_abilities_defined
    assert_abilities_defined(gate, [Authorize("posts.update"), Authorize("posts.delete")])
    ```

## Authorizing inside a handler

For per-object decisions, authorize where you have the object — `user.can(...)` returns a bool, or
`Gate.authorize(...)` raises `AuthorizationError` (→ 403):

```python
async def update_post(request, post_id):
    post = await Post.find(post_id)
    if not await request.user().can("update", post):     # routed to PostPolicy.update
        return "Forbidden", 403
    ...

# or, fail hard:
await app.make("gate").authorize("update", post, user=request.user())
```

## The web vs api groups

The default groups differ on purpose — put auth middleware where it belongs:

- **`web`** = `StartSession` → `ShareErrorsFromSession` → `ValidateCsrfToken`. Session-cookie auth and
  browser forms go here; add `AuthenticateMiddleware` (session resolver) to it.
- **`api`** = `ThrottleRequests`. Token auth goes here; your `user_resolver` reads the bearer token
  (`TokenGuard`) instead of the session.

## Common mistakes & gotchas

- **No `user_resolver` bound.** Then `AuthenticateMiddleware` always yields a guest — bind it first.
- **Confusing populate with enforce.** `AuthenticateMiddleware` only *populates* `current_user`; the
  `auth` middleware (`Authenticate`) is what *rejects* guests. You need both — populate first, then
  enforce. And the protection middleware must come *after* `AuthenticateMiddleware` in the chain.
- **Order matters.** `StartSession` must run before anything that reads the session (a session-based
  `user_resolver`, `ShareErrorsFromSession`). Keep the web group in its default order and append.
- **Wrong group.** Session middleware on a token API (or vice-versa) — match the resolver to the
  group (`web` = session, `api` = token).
- **Doing authz in middleware when it needs the object.** Per-record rules belong in the handler via
  `user.can(ability, object)`; middleware is for coarse "is this a logged-in admin?" gates.

## How it works

Service providers have two phases: **`register`** (bind into the container — no resolving other
services yet) and **`boot`** (everything is registered, so define gates/policies and read config
here). `AuthenticateMiddleware` resolves the `user_resolver` binding per request and sets the
`current_user` `ContextVar`, resetting it in a `finally` so the user never leaks between requests. The
kernel keeps named middleware **groups** and an **alias** map (`resolve_middleware` turns a string
like `"auth"` into its class); `add_route(..., group=..., middleware=[...])` composes the global
middleware, the group's stack, and any per-route middleware for each route.

## See also

- [Guards & Drivers](guards.md) — what a `user_resolver` typically calls.
- [Authentication](authentication.md) · [Authorization](authorization.md) — the primitives you wire.
- [Routes & Flows](routes-and-flows.md) — the concrete login/refresh/reset routes.
- [Service Providers](../providers.md) · [Middleware](../middleware.md) — the general mechanisms.
