# Authentication

Arvel ships a complete, production-ready auth HTTP layer you can install with a single command. If you need custom auth logic, every piece is individually replaceable.

## Quick start

```bash
uv run arvel auth:install
uv run arvel migrate
```

`auth:install` publishes four groups of files into your project:

| Tag | Files published |
|---|---|
| `config` | `config/auth.py` |
| `migrations` | `database/migrations/*_create_users_table.py`, `*_create_refresh_tokens_table.py`, `*_create_personal_access_tokens_table.py`, `*_create_password_reset_tokens_table.py` |
| `models` | `app/models/user.py` |
| `routes` | `routes/auth.py` |

Then register `AuthServiceProvider` in your app bootstrap:

```python
# bootstrap/app.py
from arvel.auth import AuthServiceProvider

app = (
    Application.configure(".")
    .with_providers([AuthServiceProvider()])
    .create()
)
```

That's it. `AuthServiceProvider` wires the guards, registers the 9 built-in endpoints, attaches `CsrfDoubleSubmitMiddleware` and `ThrottleLoginMiddleware`, and connects the event listeners that send verification and password-reset emails.

## Built-in endpoints

All routes are mounted under `AUTH_ROUTES_PREFIX` (default `/api/auth`):

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create account + send verification email |
| `POST` | `/auth/login` | Authenticate → access JWT + `__Host-refresh` cookie |
| `POST` | `/auth/refresh` | Exchange refresh cookie for new token pair |
| `POST` | `/auth/logout` | Revoke session; clear refresh cookie |
| `GET` | `/auth/me` | Return the authenticated user |
| `POST` | `/auth/forgot-password` | Request a password-reset link |
| `POST` | `/auth/reset-password` | Complete the reset with the token |
| `GET` | `/auth/verify/{signed}` | Confirm email address (signed URL) |
| `POST` | `/auth/verify/resend` | Re-send verification email |

### Token pair

`POST /auth/login` returns:

```json
{
  "access_token": "<short-lived JWT>",
  "token_type": "bearer",
  "expires_in": 900
}
```

The **refresh token** is set as an `__Host-refresh` cookie — HttpOnly, SameSite=strict, Secure-on-HTTPS. It never appears in the JSON body. Call `POST /auth/refresh` with the cookie present to get a new token pair. Refresh tokens rotate on every use; reuse of a revoked token triggers family revocation (all sessions for that user are killed).

### Rate limiting on login

`ThrottleLoginMiddleware` is applied automatically to `POST /auth/login`. By default it allows **5 attempts per 60 seconds** per IP + email combination, then returns `429 Too Many Requests` with a `Retry-After` header. You can tune this in your provider registration:

```python
from arvel.auth import AuthServiceProvider
from arvel.auth.middleware.throttle_login import ThrottleLoginMiddleware

class MyAuthServiceProvider(AuthServiceProvider):
    def make_throttle_middleware(self) -> ThrottleLoginMiddleware:
        return ThrottleLoginMiddleware(max_attempts=10, window_seconds=120)
```

## Configuration

`auth:install` publishes `config/auth.py`. The key knobs:

```python
# config/auth.py
jwt = {
    "secret": "",           # set via JWT_SECRET; must be at least 32 chars
    "algorithm": "HS256",   # or RS256
    "ttl_seconds": 900,     # 15 minutes
    "issuer": "",
    "audience": "",
}

refresh = {
    "ttl_seconds": 14 * 24 * 3600,  # 14 days
    "cookie_name": "__Host-refresh",
    "cookie_secure": True,
}

routes = {
    "enabled": True,
    "prefix": "/api/auth",
}
```

Or via environment variables:

```env
JWT_SECRET=your-32-character-minimum-secret
JWT_ISSUER=https://auth.example.com
JWT_AUDIENCE=example-api
```

## Low-level: wire up a guard manually

If you don't want the full HTTP layer, you can bind a `Guard` directly and write your own endpoints.

Arvel ships three `Guard` implementations: `SessionGuard`, `JwtGuard`, and `TokenGuard`.

```python
import os

from arvel import Application, Authenticate, Guard, JwtGuard, Route
from arvel.auth.config import JwtConfig


class MyResolver:
    async def by_id(self, user_id: str) -> object | None:
        return await users.find(user_id)

    async def by_credentials(self, credentials: dict[str, object]) -> object | None:
        user = await users.find_by_email(credentials["email"])
        if user is None:
            return None
        if not await Hash.check(credentials["password"], user.password_hash):
            return None
        return user


app = Application.configure(".").with_environment("local").create()
app.container.singleton(
    Guard,
    lambda: JwtGuard(
        resolver=MyResolver(),
        jwt=JwtConfig(secret=os.environ["JWT_SECRET"]),
    ),
)


with Route.group(middleware=[Authenticate("web")]):
    @Route.get("/me")
    async def me(): ...
```

When the guard returns a user, Arvel stashes it on `request.state.user`. When it returns `None`, Arvel raises `401 Unauthenticated`.

## SessionGuard

```python
from arvel.auth import SessionGuard

app.container.singleton(
    Guard,
    lambda c: SessionGuard(
        resolver=MyResolver(),
        session=c.resolve(SessionManager),
    ),
)
```

The session guard reads a session cookie, looks up the user via `UserResolver.by_id`, and returns them. Pair it with the [Session](session.md) middleware.

Log a user in:

```python
@Route.post("/login")
async def login(form: LoginRequest) -> dict:
    user = await resolver.by_credentials(form.validated().model_dump())
    if user is None:
        raise AuthenticationException("Invalid credentials.")
    Session.regenerate()
    Session.put("auth.user_id", user.id)
    return {"ok": True}


@Route.post("/logout")
async def logout() -> dict:
    Session.invalidate()
    return {"ok": True}
```

`Session.regenerate()` rotates the session ID to prevent fixation; `Session.invalidate()` clears the session entirely.

## JwtGuard

```python
from arvel.auth import JwtGuard
from arvel.auth.config import JwtConfig

app.container.singleton(
    Guard,
    lambda: JwtGuard(
        resolver=MyResolver(),
        jwt=JwtConfig(
            secret=os.environ["JWT_SECRET"],
            issuer="myapp",
            audience="myapp-api",
        ),
    ),
)
```

`JwtGuard` rejects two common footguns:

- **`alg=none` JWTs** — signature verification is always enforced.
- **Short HMAC secrets** — `HS*` algorithms require at least 32 characters. Arvel validates this at configuration time, so a short secret causes a startup error rather than a silent weakness in production.

Mint a token:

```python
token = await Auth.guard("api").issue_token(
    subject=str(user.id),
    expires_in=timedelta(hours=1),
    claims={"email": user.email, "role": user.role},
)
```

### Refresh tokens

For longer-lived sessions, mint a **token pair** — a short-lived access JWT and an opaque refresh token:

```python
@Route.post("/login")
async def login(form: LoginRequest, response: Response) -> dict:
    user = await resolver.by_credentials(form.validated().model_dump())
    if user is None:
        raise AuthenticationException("Invalid credentials.")
    pair = await Auth.guard("api").issue_token_pair(subject=str(user.id))
    response.set_cookie("__Host-refresh", pair.refresh_token, httponly=True, samesite="strict")
    return {"access_token": pair.access_token, "token_type": "bearer"}
```

Trade the refresh token for a new pair:

```python
@Route.post("/refresh")
async def refresh(request: Request, response: Response) -> dict:
    refresh_token = request.cookies.get("__Host-refresh")
    pair = await Auth.guard("api").refresh_tokens(refresh_token)
    if pair is None:
        raise AuthenticationException("Refresh token invalid or expired.")
    response.set_cookie("__Host-refresh", pair.refresh_token, httponly=True, samesite="strict")
    return {"access_token": pair.access_token, "token_type": "bearer"}
```

Refresh tokens rotate on each use. Refresh tokens are stored as SHA-256 hashes — the plaintext only exists in transit.

## TokenGuard

For long-lived API keys (CLI tools, service-to-service):

```python
from arvel.auth import TokenGuard

app.container.singleton(
    Guard,
    lambda c: TokenGuard(resolver=MyResolver(), store=c.resolve(TokenStore)),
)
```

Tokens are random 40-byte URL-safe strings stored as SHA-256 hashes. Generating:

```python
plaintext, persisted = await Auth.create_personal_access_token(user, name="cli-token")
# Show `plaintext` to the user once; store `persisted` in the DB.
```

## Multiple guards

```python
app.container.named(Guard, "web", lambda c: SessionGuard(...))
app.container.named(Guard, "api", lambda c: JwtGuard(resolver=..., jwt=...))

with Route.group(middleware=[Authenticate("web")]):
    @Route.get("/dashboard"): ...

with Route.group(prefix="/api", middleware=[Authenticate("api")]):
    @Route.get("/me"): ...
```

## Accessing the user

After the `Authenticate` middleware runs, the user is on the request:

```python
@Route.get("/me")
async def me(request: Request) -> dict:
    user = request.state.user
    return {"id": user.id, "email": user.email}
```

Or via the `Auth` facade:

```python
@Route.get("/me")
async def me() -> dict:
    user = await Auth.user()
    return {"id": user.id, "email": user.email}
```

## Optional authentication

`Authenticate` returns a 401 when no valid session or token is present. For routes where anonymous access is allowed but you still want to resolve the user when they *are* logged in, use `OptionalAuthenticate`:

```python
from arvel.auth.middleware import OptionalAuthenticate

with Route.group(middleware=[OptionalAuthenticate("web")]):
    @Route.get("/feed")
    async def feed(request: Request) -> dict:
        user = request.state.user   # None for anonymous visitors
        if user:
            return await personalized_feed(user)
        return await public_feed()
```

The user is attached to `request.state.user` when authenticated, and `None` otherwise — the request always proceeds.

## Where to next?

- [Password Reset](passwords.md) — the forgot-password / reset flow.
- [Email Verification](verification.md) — confirming email addresses.
- [CSRF Protection](csrf.md) — double-submit cookie pattern for SPAs.
- [Authorization](authorization.md) — gates and policies for permission checks.
- [Hashing](hashing.md) — password hashing in detail.
