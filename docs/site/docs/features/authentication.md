# Authentication

<a name="introduction"></a>
## Introduction

Many web applications provide a way for their users to authenticate and "log in". Arvel ships an authentication system built around **guards** and **user providers**, plus a `Hash` facade for password hashing and an optional set of ready-made auth endpoints.

> [!NOTE]
> Arvel's `Auth` facade is intentionally smaller than Laravel's. It covers the essential operations — `attempt`, `login`, `logout`, `user`, `check`, `id` — and every one of them takes the current `request` as an argument, because guards resolve state from the request rather than from global helpers. Laravel conveniences like `Auth.guest()`, `Auth.once()`, `via_remember`, and `login_using_id` are not implemented.

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
from arvel import Route, UnauthenticatedException
from arvel.facades.auth import Auth
from starlette.requests import Request


@Route.post("/login")
async def login(request: Request) -> dict[str, str]:
    body = await request.json()
    ok = await Auth.attempt(
        {"email": body["email"], "password": body["password"]},
        request,
    )
    if not ok:
        raise UnauthenticatedException()
    return {"status": "ok"}
```

> [!NOTE]
> `Auth.user(request)` always asks the guard — it does not read `request.state.user`. After the [`Authenticate` middleware](#protecting-routes) runs, the resolved user is also stored on `request.state.user` for direct access in a handler.

<a name="guards"></a>
## Guards

The `AuthManager` holds the configured guards and a default. Three guard types ship with the framework.

<a name="session-guard"></a>
### Session Guard

The session guard authenticates against the [session](session.md). `attempt` looks the user up via the provider, verifies the password with `Hash.check`, and on success regenerates the session and stores the user's id. `logout` forgets it.

```python
guard = Auth.guard("web")   # session guard
await Auth.attempt({"email": "ada@example.com", "password": "secret"}, request)
```

<a name="jwt-guard"></a>
### JWT Guard

The JWT guard authenticates a request from an `Authorization: Bearer <token>` header. It decodes and validates the token (signature, `exp`, optional `aud`/`iss`), requires a string `sub` claim, and rejects tokens whose `typ` isn't `access`. An invalid or expired token resolves to `None` rather than raising.

```python
guard = Auth.guard("api")   # JWT guard
token = await guard.issue_token(subject="42", expires_in=timedelta(minutes=15))
user = await guard.user(request)   # reads the bearer token
```

> [!NOTE]
> The JWT guard requires the `arvel[jwt]` extra (PyJWT). The signing secret must be at least 32 characters, and the algorithm cannot be `none` — both are enforced when the guard is built.

<a name="token-guard"></a>
### Token Guard

The token guard authenticates a hashed personal-access token from a bearer header and can scope abilities (`token.can("posts:write")`).

> [!WARNING]
> The token guard is **not fully wired** in the framework. It depends on `auth.token_repository` and `auth.user_repository` bindings that the framework does not register, so configuring the `token` driver without supplying those bindings yourself will fail at runtime. Prefer the session or JWT guards unless you provide the repositories.

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
from arvel.http.middleware import Authenticate


@Route.get("/dashboard", middleware=[Authenticate("web")])
async def dashboard(request: Request) -> dict[str, Any]:
    user = request.state.user
    return {"email": user.email}
```

Related middleware: `OptionalAuthenticate` (non-blocking — sets the user when present), `GuestMiddleware` (redirects authenticated users away from guest-only pages), `VerifiedMiddleware` (requires a verified email), and `CanMiddleware` (a [gate](authorization.md) check).

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

> [!NOTE]
> "Remember me" is not implemented. The framework deliberately omits the `LoginRequest.remember` flag and the `users.remember_token` column until a full session-guard remember-me flow ships (token rotation, hashed storage, scoped cookies).

Run `arvel auth:install` to publish the auth config, views, route stub, and migrations.

<a name="configuration"></a>
## Configuration

Authentication is configured through `AuthConfig` (published as `config/auth.py`): the default guard, the `guards` map (`web` → session, `api` → JWT), the `providers` map, JWT settings, and route options. The `AuthServiceProvider` validates the JWT secret length and algorithm when it registers.
