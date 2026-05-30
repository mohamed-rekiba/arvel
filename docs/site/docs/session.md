# Session

HTTP-driven applications are stateless. Sessions provide a way to remember things about a user across multiple requests — typically the authenticated user ID, flash messages, and CSRF tokens.

Arvel ships a multi-driver session layer that works with the `Session` facade. The same code reads and writes session data regardless of whether the backend is in-memory, Redis, the database, or a signed cookie.

## Configuration

Choose a driver via the `SESSION_DRIVER` environment variable:

| Driver | Best for | Notes |
|---|---|---|
| `memory` | Tests and single-process dev | Lost on restart, doesn't scale |
| `cookie` | Stateless apps, simple needs | Encrypted, signed; max ~4 KB |
| `redis` | Production with multiple workers | Requires `arvel[redis]` |
| `database` | Production where Redis isn't available | Slower, simpler ops |

```env
SESSION_DRIVER=redis
SESSION_LIFETIME=120          # minutes
SESSION_COOKIE=arvel_session
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=lax
SESSION_ENCRYPT=true
```

## Activating sessions

Sessions are **opt-in**. Add the session middleware to the routes that need it:

```python
from arvel.http.middleware import StartSession


with Route.group(middleware=[StartSession()]):
    @Route.get("/profile")
    async def profile(): ...
```

For most session-authenticated apps, you'll put `StartSession` at the global level. For API-only apps that use Bearer-token auth, skip it — sessions add unnecessary overhead.

See ADR-027 for the rationale behind opt-in (vs always-on) sessions.

## Reading and writing data

```python
from arvel.facades import Session


@Route.post("/welcome")
async def welcome() -> dict:
    Session.put("greeted", True)
    return {"greeted": True}


@Route.get("/")
async def home() -> dict:
    greeted = Session.get("greeted", default=False)
    return {"greeted": greeted}
```

The full API:

```python
Session.put(key, value)              # store
Session.get(key, default=None)       # read
Session.has(key)                     # exists
Session.pull(key, default=None)      # read + remove
Session.forget(key)                  # remove
Session.flush()                      # clear all
Session.all()                        # dict of everything
```

## Flash data

Flash data persists for the **next** request only — perfect for one-time messages like form errors or success notifications:

```python
@Route.post("/profile")
async def update_profile(form: UpdateProfile) -> RedirectResponse:
    ...
    Session.flash("status", "Profile updated.")
    return RedirectResponse("/profile", status_code=303)


@Route.get("/profile")
async def show_profile() -> dict:
    return {
        "user": ...,
        "status": Session.get("status"),  # auto-cleared after this request
    }
```

To keep flash data alive for one more request, use `Session.reflash()`.

## Session regeneration

Always regenerate the session ID after privilege changes (login, logout, password change). This prevents session fixation attacks:

```python
@Route.post("/login")
async def login(form: LoginRequest) -> dict:
    user = await authenticate(form.validated())
    Session.regenerate()                    # new session ID, same data
    Session.put("auth.user_id", user.id)
    return {"ok": True}


@Route.post("/logout")
async def logout() -> dict:
    Session.invalidate()                     # new ID + clear data
    return {"ok": True}
```

`Session.regenerate()` rotates the session ID without losing data. `Session.invalidate()` rotates the ID **and** flushes all data.

## Cookie-driver caveats

The cookie driver is convenient but has limits:

- **Size**: Browsers cap cookies at ~4 KB. Don't put large objects in session.
- **Encryption**: Cookie sessions are encrypted with `APP_KEY`. If the key leaks, attackers can read (and forge) sessions.
- **Bandwidth**: Every request carries the full cookie. Keep payloads small.

For anything beyond simple flash messages and user IDs, use Redis or the database driver.

## Testing with sessions

```python
async def test_login_sets_session(client) -> None:
    Session.fake()  # in-memory recorder
    response = await client.post("/login", json={"email": "a@b.com", "password": "..."})
    assert response.status_code == 200
    assert Session.has("auth.user_id")
```

## Where to next?

- [Authentication](authentication.md) — session-backed auth via `SessionGuard`.
- [CSRF](csrf.md) — depends on the session for token storage.
- [Configuration](configuration.md) — env vars for session drivers.
