# Authentication

Authentication answers one question: **is this request really who it claims to be?** The classic
answer is a password — the user hands you an email and a secret, you check the secret against a hash
you stored, and if it matches you remember them for the rest of the session. This page covers exactly
that: making your user model authenticatable, verifying credentials, and managing the logged-in
session. Logging in through Google or Keycloak instead of a password is the same idea with a
different proof — that's [single sign-on](sso-oidc.md); the *session* half below is identical.

## Make your user model authenticatable

Mix `Authenticatable` into your `User` model. It adds the small contract the auth system needs — an
identifier and (for password login) a hashed credential:

```python
from arvel import Model
from arvel.auth import Authenticatable

class User(Model, Authenticatable):
    __fields__   = {"email": str, "name": str, "password": str}
    __fillable__ = ["email", "name"]          # note: password is NOT mass-assignable
```

`Authenticatable` gives every instance `get_auth_identifier()` (the primary key by default) and
`get_auth_password()` (reads the `password` attribute) — plus `await user.can(...)` for
[authorization](authorization.md) checks.

!!! warning "Never store a plaintext password"
    Hash it on the way in and only ever compare hashes. arvel's `Hasher` wraps Argon2 (via pwdlib):

    ```python
    from arvel.security import Hasher

    user = await User.create(email="ada@example.com", name="Ada")
    user.password = Hasher().make("correct-horse-battery-staple")  # guarded → set directly
    await user.save()
    ```

## Logging a user in

`AuthManager` is the session — it tracks the current user and verifies credentials. The heart of it
is `attempt()`: you give it the submitted credentials and a **user-provider** callable that finds the
matching user; it verifies the password and, on success, logs them in.

```python
from arvel.auth import AuthManager

auth = AuthManager()

async def find_user(credentials: dict) -> User | None:
    return await User.where(email=credentials["email"]).first()

async def login(request):
    credentials = await request.form()                 # {"email": ..., "password": ...}
    if await auth.attempt(credentials, find_user):
        return redirect("/dashboard")                  # logged in — session remembers them
    return "Invalid credentials", 401
```

`attempt` returns `True` only when the user exists **and** the password matches the stored hash; it
never reveals which half failed (don't leak whether an email is registered).

## The session: who's logged in?

Once someone is authenticated, `AuthManager` exposes the session over a request-scoped
`current_user`:

```python
auth.user()        # the User instance, or None
auth.check()       # True if someone is logged in
auth.guest()       # True if nobody is
auth.id()          # the current user's identifier, or None

auth.login(user)   # log a user in directly (e.g. right after registration)
auth.logout()      # forget them
```

In a request handler you usually reach for the active user through the request:

```python
async def profile(request):
    user = request.user()              # the same current_user
    if user is None:
        return redirect("/login")
    return {"email": user.email}
```

The current user is stored in a `ContextVar`, so it is **isolated per request / per async task** —
two concurrent requests never see each other's user.

!!! warning "`AuthManager.login`/`attempt` don't persist a session"
    `auth.login(user)` only sets the `current_user` ContextVar — it's the right call from a **non-HTTP**
    context (a job, a console command) where there's no request to persist to, but on its own it means
    every request re-authenticates from scratch. For a web login, use `SessionGuard.login` below.

## Logging in over HTTP (`SessionGuard`)

A browser session needs two things `AuthManager.login` doesn't do: **rotate the session id** (so a
pre-login, possibly attacker-fixed, id is never reused — session fixation) and **persist the user id**
to the session (so the *next* request is still logged in). `arvel.auth.guards.SessionGuard` does both:

```python
from arvel.auth.guards import SessionGuard

async def login(request):
    credentials = await request.form()
    user = await find_user(credentials)
    if user is None or not await auth.attempt(credentials, find_user):
        return "Invalid credentials", 401
    await SessionGuard().login(user, request, remember=bool(credentials.get("remember")))
    return redirect("/dashboard")

async def logout(request):
    await SessionGuard().logout(request)
    return redirect("/")
```

`login(user, request, *, remember=False)` regenerates the session id **before** writing the user id
(fixation defence), sets `current_user` for the rest of this request, and — when `remember` — issues a
rotating remember-me cookie ([Routes & Flows](routes-and-flows.md#stay-logged-in-remember-me)).
`logout(request)` clears the remember cookie/token, invalidates the session (new id, all data
dropped), and clears `current_user`.

### Wiring the *read* half: `user_resolver`

Persisting the user id to the session is only half the story — something has to read it back on the
*next* request. That's the app's `user_resolver` binding ([Providers &
middleware](providers-and-middleware.md)); `SessionGuard.user_id(request)` is the primitive it calls
for a session-based app (mirrors `TokenGuard.user_id(request)` for the bearer-token path):

```python
async def resolve_user(request):
    user_id = await SessionGuard().user_id(request)   # reads back what login() persisted
    return await User.find(user_id) if user_id is not None else None

self.app.singleton("user_resolver", lambda app: resolve_user)
```

Without this, `login()` still rotates/persists correctly, but `AuthenticateMiddleware` has nothing to
read it back with — every request but the login one itself looks like a guest.

## The local guard

Under the hood, "verify a request by some method" is the job of a **guard** (the full system is in
[Guards & Drivers](guards.md)). The one behind password login is the `local` guard, and you can use
it directly — it reads `email`/`username` + `password` from the submitted form and returns a
[`Principal`](guards.md) on success:

```python
from arvel.auth.guards import GuardManager

guard = GuardManager().guard("local")
principal = await guard.verify(request)    # Principal(provider="local", subject="ada@example.com") or None
```

`attempt()` above is the convenient session-aware wrapper; the guard is the lower-level primitive you
reach for when you're composing your own flow or running more than one authentication method.

## Throttling logins (brute-force lockout)

Unlimited password guesses are a brute-force invitation. Give `AuthManager` a **`LoginRateLimiter`**
and it locks out an identifier after too many failures within a window — counted over the cache, so
the limit holds across processes:

```python
from arvel.auth import AuthManager
from arvel.auth.throttle import LoginRateLimiter
from arvel.cache import CacheManager

limiter = LoginRateLimiter(CacheManager().driver("redis"), max_attempts=5, decay_seconds=900)
auth = AuthManager(limiter=limiter)

await auth.attempt(credentials, find_user)   # a locked-out identifier fails fast (no password check)
```

While locked, `attempt` returns `False` even for the *correct* password; each failed try is counted
and a successful login clears the counter. Show the user when they can retry:

```python
if await limiter.too_many_attempts(email):
    return f"Too many attempts. Try again in {await limiter.available_in(email)}s.", 429
```

Without a `limiter`, `AuthManager` doesn't throttle — it's opt-in. The identifier is normalised
(case/whitespace) so `Ada@x` and `ada@x` share one bucket, and on a **cache outage** the limiter
**fails open** by default (logins still work, but throttling is off — alert on cache downtime); pass
`fail_open=False` to fail closed instead.

!!! tip "Layer in IP throttling"
    Identifier-only lockout lets someone lock a *known* email out for the window. Put the IP-keyed
    [`ThrottleRequests`](../middleware.md) in front of the login route for a second dimension.

## Confirming a password (sudo mode)

Some actions — changing email, deleting the account, rotating keys — should re-verify the password
even for an already-logged-in user. `confirm_password` checks it and records a *confirmed-at* stamp in
the session; `EnsurePasswordConfirmed` middleware then gates the sensitive routes:

```python
from arvel.auth.confirm import confirm_password, EnsurePasswordConfirmed

async def confirm(request):                       # the "confirm your password" form posts here
    if await confirm_password(request, (await request.form())["password"]):
        return redirect(request.query("next") or "/settings")
    return "Incorrect password", 422

kernel.alias({"password.confirm": EnsurePasswordConfirmed})
kernel.add_route(["DELETE"], "/account", close_account, group="web", middleware=["password.confirm"])
```

A route behind `password.confirm` returns **403** until the password was confirmed within the window
(default 3h; subclass `EnsurePasswordConfirmed` to change it). It needs the session, so use it in the
`web` group behind `StartSession`.

Re-confirming a password is an online guessing surface, so throttle it the same way you throttle
login — pass a [`LoginRateLimiter`](#throttling-logins-brute-force-lockout):

```python
await confirm_password(request, password, limiter=limiter)   # keyed by the user id by default
```

A locked key fails fast (no password check), each wrong password is counted, a success clears it, and
every wrong/locked attempt is audited on the `security` channel (`auth.password_confirm.failed` /
`.locked`).

## Common mistakes & gotchas

- **Storing or comparing plaintext.** Always `Hasher().make(...)` on the way in and let `attempt` /
  the guard do the comparison. Never `==` a password.
- **Leaking which field was wrong.** `attempt` deliberately returns a single boolean — show one
  "invalid credentials" message, not "no such email" vs "wrong password."
- **Putting `password` in `__fillable__`.** Keep it out of mass-assignment and set it explicitly,
  so a stray form field can't overwrite a hash.
- **Reading `auth.user()` outside a request.** The current user lives in a `ContextVar` scoped to
  the request/task; in a job or CLI command there's no session user — pass the user explicitly.
- **Expecting `attempt` to persist a cookie for you.** It establishes the in-process session user;
  wiring it to a session cookie/middleware is the app's responsibility (see [Middleware](../middleware.md)).

## How it works

`AuthManager` holds the current user in a `current_user` `ContextVar`. `attempt(credentials,
provider)` resolves the user via your callable, then routes the password check through the **`local`
guard** — which compares the submitted secret against the stored hash with `security.Hasher` (Argon2,
constant-time). On success it calls `login()`, which sets the context variable; `logout()` clears it.
Because the store is a `ContextVar`, the session is concurrency-safe without any thread-local
juggling.

**Rehash-on-login:** when a correct login presents a password whose stored hash is outdated (e.g. you
later raised the Argon2 cost), `attempt` transparently re-hashes it with the current parameters and
saves — hashes upgrade themselves as users sign in. It's a no-op for a current hash, a wrong
password, or a user that can't persist (override `set_auth_password` if your hash lives on a
non-`password` field).

## See also

- [Guards & Drivers](guards.md) — the engine behind every login method, and how to run several.
- [Identities & Account Linking](identities.md) — let one person log in by password *and* SSO.
- [Single Sign-On (OIDC / Keycloak)](sso-oidc.md) — authenticate through an identity provider.
- [Authorization](authorization.md) — once you know *who* they are, decide *what they may do*.
