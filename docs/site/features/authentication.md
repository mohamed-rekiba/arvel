# Authentication

<a name="introduction"></a>
## Introduction

Many web applications provide a way for their users to authenticate and "log in". Arvel ships an authentication system built around **guards** and **user providers**, plus a `Hash` facade for password hashing and an optional set of ready-made auth endpoints.

> [!NOTE]
> Arvel's `Auth` facade is intentionally smaller than Laravel's. It covers the essential operations — `attempt`, `login`, `logout`, `user`, `check`, `id` — and every one of them takes the current `request` as an argument, because guards resolve state from the request rather than from global helpers. Laravel conveniences like `Auth.guest()`, `Auth.once()`, `via_remember`, and `login_using_id` are not implemented.

<a name="quick-start"></a>
### Quick start

Install auth stubs, register the provider, migrate, then log users in or protect routes:

```bash
arvel auth:install
arvel migrate
```

```python
# bootstrap/providers.py
from arvel.auth.provider import AuthServiceProvider

providers = [
    AuthServiceProvider,
    # ...
]
```

```python
from pydantic import BaseModel

from app.models.user import User
from arvel import Route, UnauthenticatedException
from arvel.facades.auth import Auth
from arvel.http import Request
from arvel.http.middleware import Authenticate


class Credentials(BaseModel):
    email: str
    password: str


@Route.post("/login")
async def login(payload: Credentials, request: Request) -> dict[str, str]:
    # payload is parsed and validated by the routing layer — no await request.json().
    if not await Auth.attempt({"email": payload.email, "password": payload.password}, request):
        raise UnauthenticatedException()
    return {"status": "ok"}


@Route.get("/me", middleware=[Authenticate("api")])
async def me(request: Request) -> dict[str, str]:
    # request.state.user is set dynamically by Authenticate — annotate it so the
    # rest of the handler is type-checked against your model.
    user: User = request.state.user
    return {"email": user.email}
```

Prefer batteries-included JSON endpoints? With `config.routes.enabled` true (the default), [`AuthServiceProvider`](#registering-the-provider) mounts [built-in `/api/auth/*` routes](#built-in-auth-routes) — register, login, refresh, logout, and `me` without writing handlers.

| Goal | Read next |
|---|---|
| Cookie / session login | [Session guard](#session-guard) + [Session](session.md) |
| Bearer JWT | [JWT guard](#jwt-guard) |
| API tokens with scoped abilities | [Token guard](#token-guard) |
| Ready-made login/refresh/logout endpoints | [Built-in auth routes](#built-in-auth-routes) |
| Password hashing | [Password hashing](#password-hashing) |
| Who can do what | [Authorization](authorization.md) |

<a name="registering-the-provider"></a>
## Registering the Provider

Authentication is **opt-in**. Add `AuthServiceProvider` to `bootstrap/providers.py`:

```python
# bootstrap/providers.py
from arvel.auth.provider import AuthServiceProvider

providers = [
    # ...other providers...
    AuthServiceProvider,
]
```

Without it, the `Auth` facade, the [`Gate`](authorization.md), and the built-in `/api/auth/*` routes are all unavailable. The provider binds the `AuthManager` (wiring the `Auth` facade), registers the `Gate` singleton, and — when `config.routes.enabled` is true — mounts the [auth endpoints](#built-in-auth-routes).

<a name="guards-and-providers"></a>
### Guards & Providers

Authentication has two halves:

- **Guards** define how users are authenticated for each request — a session guard reads a cookie-backed session; a JWT guard reads a bearer token.
- **User providers** define how users are retrieved from storage — typically a database lookup against your `User` model.

<a name="the-auth-facade"></a>
## The Auth Facade

Import the facade from its module and pass the request:

```python
from arvel.facades.auth import Auth
```

| Method | Async | Description |
|---|---|---|
| `Auth.attempt(credentials, request)` | yes | Attempt to authenticate with credentials; returns `bool` |
| `Auth.login(user, request)` | yes | Log a user in on the default guard |
| `Auth.logout(request)` | yes | Log the current user out |
| `Auth.user(request)` | yes | The authenticated user, or `None` |
| `Auth.check(request)` | yes | `True` if a user is authenticated |
| `Auth.id(request)` | yes | The authenticated user's id as a string, or `None` |
| `Auth.guard(name)` | no | Get a specific guard |
| `Auth.set_manager(manager)` | no | Bind the `AuthManager` (done by the provider) |

```python
from pydantic import BaseModel

from arvel import Route, UnauthenticatedException
from arvel.facades.auth import Auth
from arvel.http import Request


class Credentials(BaseModel):
    email: str
    password: str


@Route.post("/login")
async def login(payload: Credentials, request: Request) -> dict[str, str]:
    if not await Auth.attempt({"email": payload.email, "password": payload.password}, request):
        raise UnauthenticatedException()
    return {"status": "ok"}
```

> [!NOTE]
> `Auth.user(request)` always asks the guard — it does not read `request.state.user`. After the [`Authenticate` middleware](#protecting-routes) runs, the resolved user is also stored on `request.state.user` for direct access in a handler. Because `request.state` is dynamically typed, annotate the local (`user: User = request.state.user`) to keep the handler type-checked — that's the pattern used throughout these examples.

<a name="guards"></a>
## Guards

The `AuthManager` holds the configured guards and a default. Three guard types ship with the framework.

<a name="session-guard"></a>
### Session Guard

The session guard is the cookie-backed "web" login. `attempt` looks the user up via the provider, verifies the password with `Hash.check`, and on success regenerates the session (fixation defence) and stores the user's id under `_auth_id`. `user` reads that id back; `logout` forgets it. It needs the [`StartSession`](session.md) middleware in front of it so `request.state.session` exists.

End to end — register, log in, read the user, log out:

```python
from pydantic import BaseModel

from app.models.user import User
from arvel import Route, UnauthenticatedException
from arvel.facades.auth import Auth
from arvel.facades.hash import Hash
from arvel.http import Request
from arvel.http.middleware import Authenticate


class Credentials(BaseModel):
    email: str
    password: str


@Route.post("/register")
async def register(payload: Credentials) -> dict[str, str]:
    await User.create(email=payload.email, password=Hash.make(payload.password))
    return {"status": "registered"}


@Route.post("/login")
async def login(payload: Credentials, request: Request) -> dict[str, str]:
    # attempt() verifies the password, regenerates the session, writes _auth_id.
    if not await Auth.attempt({"email": payload.email, "password": payload.password}, request):
        raise UnauthenticatedException()
    return {"status": "ok"}


@Route.get("/dashboard", middleware=[Authenticate("web")])
async def dashboard(request: Request) -> dict[str, str]:
    user: User = request.state.user   # resolved from the session cookie
    return {"email": user.email}


@Route.post("/logout")
async def logout(request: Request) -> dict[str, str]:
    await Auth.logout(request)   # forgets _auth_id; the cookie is now anonymous
    return {"status": "ok"}
```

The browser holds nothing but the session cookie — the user id lives server-side in the session store. Swap the store (array, file, Redis) without touching this code; see [Session](session.md).

<a name="jwt-guard"></a>
### JWT Guard

The JWT guard is the stateless bearer-token path — no cookie, no server-side session. The signed token *is* the credential. The guard decodes and validates it (signature, `exp`, optional `aud`/`iss`), requires a string `sub` claim, and rejects tokens whose `typ` isn't `access`. An invalid or expired token resolves to `None` rather than raising.

End to end — issue a token on login, send it as a bearer, read the user:

```python
from datetime import timedelta

from pydantic import BaseModel

from app.models.user import User
from arvel import Route, UnauthenticatedException
from arvel.auth.guards.jwt import JwtGuard
from arvel.facades.auth import Auth
from arvel.facades.hash import Hash
from arvel.http import Request
from arvel.http.middleware import Authenticate


class Credentials(BaseModel):
    email: str
    password: str


@Route.post("/api/login")
async def api_login(payload: Credentials) -> dict[str, str]:
    user: User | None = await User.first_where(email=payload.email)
    if user is None or not Hash.check(payload.password, user.password):
        raise UnauthenticatedException()

    guard = Auth.guard("api")            # the JWT guard
    assert isinstance(guard, JwtGuard)   # narrows the type for issue_token
    access = await guard.issue_token(
        subject=str(user.id),            # becomes the `sub` claim
        expires_in=timedelta(minutes=15),
    )
    return {"access_token": access, "token_type": "Bearer"}


@Route.get("/api/me", middleware=[Authenticate("api")])
async def api_me(request: Request) -> dict[str, str]:
    user: User = request.state.user   # client sent `Authorization: Bearer <access_token>`
    return {"email": user.email}
```

Because the token is self-contained, validating it touches no database — only the `sub` lookup does.

> [!NOTE]
> The JWT guard requires the `arvel[jwt]` extra (PyJWT). The signing secret must be at least 32 characters, and the algorithm cannot be `none` — both are enforced when the guard is built.

A raw JWT is valid until its `exp` with no way to take it back — until you add the denylist (see [Revoking access tokens](#revoking-tokens)). Or skip manual issuing entirely and use the [built-in `/api/auth/*` routes](#built-in-auth-routes), which pair short-lived access JWTs with rotating refresh tokens.

<a name="token-guard"></a>
### Token Guard

The token guard is the Sanctum-style path for long-lived API or machine tokens — opaque bearer tokens you mint per client, each scoped to a set of **abilities**. No refresh cycle, no cookie. The framework wires it out of the box with `ArventTokenRepository` and `MorphUserRepository`; you don't register anything beyond the guard config.

#### Abilities, start to end

This is the full lifecycle of an ability — from minting the token to enforcing the scope in a handler.

**1. Make the model token-aware.** Add the `HasApiTokens` mixin:

```python
# app/models/user.py
from arvel.auth.mixins import Authenticatable, HasApiTokens
from arvel.database import Model, Timestamps, id_, string


class User(Model, Timestamps, Authenticatable, HasApiTokens):
    __tablename__ = "users"
    _auth_password_field = "password"

    id: int = id_()
    email: str = string(255, unique=True)
    password: str = string(255)
```

**2. Mint a token with abilities.** The plaintext is returned **once** — only its SHA-256 digest is stored. Abilities are arbitrary scope strings you define; `["*"]` grants everything:

```python
# scopes this token to two abilities — nothing else
plain = await user.create_token("ci-bot", abilities=["posts:read", "posts:write"])
# hand `plain` to the client; you can never read it back
```

**3. Point a guard at the `token` driver:**

```python
# config/auth.py
guards = {"api": {"driver": "token", "provider": "users"}}
```

**4. The client sends it as a bearer.** On each request the guard hashes the incoming plaintext, looks the row up in `personal_access_tokens`, confirms the digest in constant time, rejects expired tokens, resolves the owning model from the token's polymorphic `tokenable_type` + `tokenable_id`, bumps `last_used_at`, and **attaches the token to the resolved user**.

**5. Enforce the ability in the handler.** The token rides on the per-request user, so check it with `token_can`:

```python
from app.models.user import User
from arvel import AuthorizationException, Route
from arvel.http import Request
from arvel.http.middleware import Authenticate


@Route.post("/api/posts", middleware=[Authenticate("api")])
async def create_post(request: Request) -> dict[str, str]:
    user: User = request.state.user            # resolved + token attached
    if not user.token_can("posts:write"):      # this token's scope
        raise AuthorizationException("Token lacks posts:write.")
    # ... create the post ...
    return {"status": "created"}
```

A token minted with `["posts:read"]` fails that check; one minted with `["posts:write"]` or `["*"]` passes. `user.current_access_token()` returns the underlying [`PersonalAccessToken`](#built-in-auth-routes) if you need its name, abilities, or `last_used_at`; for non-token guards it's `None`.

> [!NOTE]
> Abilities are scoped to the **per-request user**, not the guard — `AuthManager` is a singleton, so the guard object is shared across all requests, but each request resolves its own user and carries its own token. That keeps `token_can` correct under concurrency. Check abilities through `user.token_can(...)`, never off the guard.

> [!NOTE]
> Only top-level model classes can own tokens — the fully-qualified `tokenable_type` of a nested class can't round-trip through an import.

For role/permission-style checks that aren't tied to an API token (policies, gates, the `CanMiddleware`), see [Authorization](authorization.md). Token abilities and Gate policies compose: a token can carry `posts:write` *and* the user still has to pass the post's [policy](authorization.md).

<a name="user-providers"></a>
## User Providers

The only built-in provider is the **arvent provider**, which looks users up against an Arvent model. It finds users by primary key (`by_id`) and by a username field (`by_credentials`, default `email`):

```python
# config/auth.py (published by `arvel auth:install`)
providers = {
    "users": {"driver": "database", "model": "app.models.user.User"},
}
```

<a name="the-authenticatable-mixin"></a>
### The Authenticatable Mixin

A user model becomes authenticatable through the `Authenticatable` mixin, which exposes `get_auth_id()` and `get_auth_password()`. The password column defaults to `password_hash`, but the shipped `User` model overrides it to `password`:

```python
from arvel.auth.mixins import Authenticatable
from arvel.database import Model, Timestamps, id_, string


class User(Model, Timestamps, Authenticatable):
    __tablename__ = "users"
    _auth_password_field = "password"

    id: int = id_()
    email: str = string(255, unique=True)
    password: str = string(255)
```

<a name="protecting-routes"></a>
## Protecting Routes

Attach the `Authenticate` middleware to require an authenticated user. It resolves the named guard, stores the user on `request.state.user`, binds the user id into the logging [context](logging.md), and raises an unauthenticated exception (translated to **401**) when no user is present:

```python
from app.models.user import User
from arvel import Route
from arvel.http import Request
from arvel.http.middleware import Authenticate


@Route.get("/dashboard", middleware=[Authenticate("web")])
async def dashboard(request: Request) -> dict[str, str]:
    user: User = request.state.user
    return {"email": user.email}
```

Related middleware: `OptionalAuthenticate` (non-blocking — sets the user when present), `GuestMiddleware` (redirects authenticated users away from guest-only pages), `VerifiedMiddleware` (requires a verified email), and `CanMiddleware` (a [gate](authorization.md) check).

`VerifiedMiddleware` distinguishes the two failure cases: no authenticated user is a **401** (log in first), while a logged-in user whose email isn't verified is a **403** (re-authenticating won't help — they have to verify their email).

<a name="password-hashing"></a>
## Password Hashing

The `Hash` facade hashes and verifies passwords. The default algorithm is **argon2id**:

```python
from arvel.facades.hash import Hash

hashed = Hash.make("plain-text-password")
ok = Hash.check("plain-text-password", hashed)
if Hash.needs_rehash(hashed):
    hashed = Hash.make("plain-text-password")
```

`Hash.make_bcrypt(password, rounds=12)` is available if you install the `arvel[bcrypt]` extra. All `Hash` methods are synchronous.

`Hash.check` and `Hash.needs_rehash` are algorithm-aware: they dispatch on the hash's own prefix (`$argon2…` vs bcrypt's `$2…`). So a bcrypt hash — including a `$2y$` column imported from an existing Laravel app — verifies through `Hash.check` without any extra wiring, and `Hash.needs_rehash` returns `True` for it so the next successful login transparently upgrades it to argon2id.

> [!NOTE]
> Although a `HashConfig` exists with a `bcrypt` default, the `Hash` facade does not read it — it uses argon2id directly. Ignore the `hashing` block in the published config stub.

<a name="built-in-auth-routes"></a>
## Built-in Auth Routes

With [`AuthServiceProvider` registered](#registering-the-provider) and `config.routes.enabled` true (the default), the provider mounts a set of JSON auth endpoints under `/api/auth`:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | Register a user (201) |
| `POST` | `/api/auth/login` | Log in; sets refresh + CSRF cookies |
| `POST` | `/api/auth/refresh` | Rotate the refresh token |
| `POST` | `/api/auth/logout` | Log out (204) |
| `GET` | `/api/auth/me` | The current user (bearer JWT) |
| `POST` | `/api/auth/forgot-password` | Begin a password reset (202) |
| `POST` | `/api/auth/reset-password` | Complete a password reset |
| `GET` | `/api/auth/verify/{signed}` | Verify an email via signed URL |
| `POST` | `/api/auth/verify/resend` | Resend verification (rate-limited) |

These are backed by `AuthService` (register/login/refresh/logout/me), `PasswordService` (forgot/reset), and `EmailVerificationService`. Access tokens are JWTs; refresh tokens are opaque, stored as SHA-256 digests in a `refresh_tokens` table and rotated on use.

<a name="revoking-tokens"></a>
### Revoking access tokens

A JWT is valid until its `exp` — there's no taking it back without server-side state. Arvel keeps that state in a Cache-backed denylist, so revocation works the moment it happens instead of waiting out the access TTL:

- **Logout** denies the presented access token's `jti`. The token stops working right away; the user's other sessions keep theirs.
- **Password reset** and **refresh-token-reuse detection** revoke *every* outstanding access token for the user (a cutoff on `iat`), not just the refresh rows. A reset ends every session.

The denylist lives in the Cache subsystem, so it's shared across workers when you configure a Redis cache. The default array/in-process cache is single-process only. Checks **fail open**: if the cache is unavailable, a token is treated as not-revoked rather than rejecting everyone — a cache outage shouldn't lock out the whole app.

> [!NOTE]
> Login attempts are throttled by `ThrottleLoginMiddleware`. By default the counter is process-local; pass `ThrottleLoginConfig(store=CacheLoginAttemptStore())` to share the limit across workers via the cache.

> [!NOTE]
> "Remember me" is not implemented. The framework deliberately omits the `LoginRequest.remember` flag and the `users.remember_token` column until a full session-guard remember-me flow ships (token rotation, hashed storage, scoped cookies).

Run `arvel auth:install` to publish the auth config, views, route stub, and migrations.

<a name="configuration"></a>
## Configuration

Authentication is configured through `AuthConfig` (published as `config/auth.py`): the default guard, the `guards` map (`web` → session, `api` → JWT), the `providers` map, JWT settings, and route options. The `AuthServiceProvider` validates the JWT secret length and algorithm when it registers.
