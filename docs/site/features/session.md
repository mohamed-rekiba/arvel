# Session

<a name="introduction"></a>
## Introduction

Since HTTP-driven applications are stateless, sessions provide a way to store information about the user across multiple requests. Arvel stores that information server-side and ships a signed session-id cookie to the browser.

> [!NOTE]
> Unlike Laravel, the `Session` facade is intentionally thin — it exposes only `Session.manager()`. The day-to-day read/write API lives on the per-request `SessionData` object, which you reach through `request.state.session`.

<a name="quick-start"></a>
### Quick start

Register the provider and wire `StartSession` as ASGI middleware (not route middleware — see [Enabling sessions](#enabling-sessions)):

```python
# bootstrap/providers.py
from arvel.providers.session_provider import SessionServiceProvider

providers = [SessionServiceProvider, ...]
```

```python
from starlette.middleware import Middleware

from arvel.facades.session import Session
from arvel.session.middleware import SessionCookie, StartSession

middleware = [
    Middleware(
        StartSession,
        store=Session.manager().store(),
        options=SessionCookie(lifetime=7200),
    ),
]
```

Read and write session data on any request that passes through that stack:

```python
from starlette.requests import Request


async def set_theme(request: Request) -> dict[str, str]:
    session = request.state.session
    session.put("theme", "dark")
    session.flash("status", "Preference saved")
    return {"theme": session.get("theme")}
```

The [session guard](authentication.md#session-guard) stores the authenticated user id in this same session — `SessionGuard.login()` calls `session.regenerate()` for you after a successful login.

| Task | API |
|---|---|
| Read / write | `session.get(...)`, `session.put(...)` |
| One-request messages | `session.flash(...)` — [Flash data](#flash-data) |
| After login | `session.regenerate()` — [Regenerating the session ID](#regenerating-the-session-id) |

<a name="configuration"></a>
## Configuration

Sessions read `config/session.py` when present; the `SESSION_*` environment variables are the fallback for any key the file doesn't set (see [the cascade](../core-concepts/configuration.md#the-cascade)):

```ini
SESSION_DRIVER=cookie
SESSION_LIFETIME=7200
SESSION_COOKIE_NAME=arvel_session
SESSION_FILES_PATH=storage/framework/sessions
```

<a name="drivers"></a>
### Drivers

| Driver | Backing store | Notes |
|---|---|---|
| `cookie` | The cookie itself | Default; stateless, size-limited |
| `file` | Files on disk | Server-side, good for local dev |
| `redis` | Redis | Requires `arvel[redis]` |
| `database` | A `sessions` table | Ship the bundled migration |
| `array` | An in-process dict | **Test-only**; resets per process, leaves no on-disk state |

<a name="enabling-sessions"></a>
### Enabling Sessions

Sessions are **opt-in**. Register `SessionServiceProvider` (it binds the `Session` facade), then add `StartSession` to the ASGI middleware stack. `StartSession` is pure ASGI middleware — it loads the session at the start of the request, attaches it to `request.state.session`, and writes it back when the response finishes. It takes a `store` (from `Session.manager().store()`) plus a `SessionCookie` describing the Set-Cookie flags:

```python
from starlette.middleware import Middleware
from arvel.config import Config, SessionConfig
from arvel.facades.session import Session
from arvel.session.middleware import SessionCookie, StartSession

cfg = Config.of(SessionConfig)
store = Session.manager().store()
cookie = SessionCookie(
    name=cfg.cookie_name,
    lifetime=cfg.lifetime,
    secure=cfg.secure,
    same_site=cfg.same_site,
)
middleware = [Middleware(StartSession, store=store, options=cookie)]
```

> [!NOTE]
> `StartSession` is not a route-level middleware alias — there's no `"session"` group registered by the provider. Wire it as ASGI middleware on the app.

> [!NOTE]
> The session id cookie is always `HttpOnly` with `Path=/`. Pass `secure` and `same_site` via `SessionCookie` (from `SESSION_SECURE`/`SESSION_SAME_SITE`) to control the rest. `same_site="none"` forces `Secure` on, since browsers reject `SameSite=None` cookies without it.

<a name="interacting-with-the-session"></a>
## Interacting With the Session

Reach the session through the request:

```python
async def show(request: Request) -> dict[str, Any]:
    session = request.state.session   # SessionData
    ...
```

<a name="retrieving-data"></a>
### Retrieving Data

```python
value = session.get("key")
value = session.get("key", "default")
exists = session.has("key")
everything = session.all()
```

<a name="storing-data"></a>
### Storing Data

```python
session.put("key", "value")
```

<a name="deleting-data"></a>
### Deleting Data

```python
session.forget("key")    # remove a single key
session.flush()          # remove everything (keeps the session id)
```

<a name="flash-data"></a>
## Flash Data

Flash data lives for exactly one subsequent request — ideal for status messages after a redirect. `flash` stores a value readable on the **next** request; `now` stores one readable only on the **current** request:

```python
session.flash("status", "Profile updated!")   # available next request
session.now("alert", "Heads up")               # available this request only
session.reflash()                              # keep current flash one more request
```

The `StartSession` middleware ages flash data automatically: new flash from one request becomes readable flash on the next, then expires.

<a name="regenerating-the-session-id"></a>
## Regenerating the Session ID

Regenerate the session id after authentication to prevent session fixation:

```python
session.regenerate()
```

`regenerate()` rotates to a fresh id **and** destroys the old record in the store when the response finishes — the pre-login session can't outlive the rotation. This matches Laravel's `migrate(true)`. `SessionGuard.login()` calls it for you, so a returning visitor who logs in won't leave their guest session readable in the backend.
