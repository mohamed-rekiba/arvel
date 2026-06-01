# Session

<a name="introduction"></a>
## Introduction

Since HTTP-driven applications are stateless, sessions provide a way to store information about the user across multiple requests. Arvel stores that information server-side and ships a signed session-id cookie to the browser.

> [!NOTE]
> Unlike Laravel, the `Session` facade is intentionally thin — it exposes only `Session.manager()`. The day-to-day read/write API lives on the per-request `SessionData` object, which you reach through `request.state.session`.

<a name="configuration"></a>
## Configuration

Sessions are configured through the `SESSION_*` environment variables:

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

<a name="enabling-sessions"></a>
### Enabling Sessions

Sessions are **opt-in**. Register `SessionServiceProvider` (it binds the `Session` facade), then add `StartSession` to the ASGI middleware stack. `StartSession` is pure ASGI middleware — it loads the session at the start of the request, attaches it to `request.state.session`, and writes it back when the response finishes. It takes a `store` (from `Session.manager().store()`) plus `lifetime` and `cookie_name`:

```python
from starlette.middleware import Middleware
from arvel.facades.session import Session
from arvel.session.middleware import StartSession

store = Session.manager().store()
middleware = [Middleware(StartSession, store=store, lifetime=7200)]
```

> [!NOTE]
> `StartSession` is not a route-level middleware alias — there's no `"session"` group registered by the provider. Wire it as ASGI middleware on the app.

> [!NOTE]
> The session id cookie is set with `HttpOnly`, `Path=/`, and `SameSite=Lax`. It is **not** marked `Secure`, so serve session-bearing routes over HTTPS in production and terminate TLS in front of the app.

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
