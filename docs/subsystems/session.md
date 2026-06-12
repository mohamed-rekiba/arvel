# Session

`SessionManager` selects a store; `StartSession` middleware reads the cookie, attaches session data to the request, and writes it back on response.

**Source**: `packages/arvel/src/arvel/session/` — `manager.py`, `store.py`, `stores/`, `middleware.py`, `providers/`, `config/session_config.py`.

## Stores

```python
class SessionStore(Protocol):
    async def read(self, session_id) -> dict[str, Any]: ...
    async def write(self, session_id, data) -> None: ...
    async def destroy(self, session_id) -> None: ...
    async def gc(self, max_lifetime) -> int: ...
```

Session lifetime is configured on the store at construction (`SessionConfig.lifetime` from `SESSION_LIFETIME`) — not passed per `write()`. That matches Laravel's `SessionHandlerInterface::write()`, which also takes no TTL argument. `StartSession` sets the cookie `Max-Age` from `SessionCookie.lifetime`; server-side stores use the same configured value for expiry (file mtime, DB `last_activity`, Redis TTL). `CookieStore` enforces it too — the encrypted payload carries an `expires` stamp checked on read, so a replayed cookie can't outlive `SESSION_LIFETIME` even though the browser's `Max-Age` is client-controlled (Laravel `CookieSessionHandler` parity). `SESSION_LIFETIME=0` means never-expire.

The `redis` and `database` drivers create a connection pool the manager owns. `SessionManager.shutdown()` disposes it and `SessionServiceProvider.shutdown()` calls that on teardown, so the pool drains instead of leaking until process exit.

Driver from `SessionConfig` (`SESSION_*`, default `cookie`):

| Driver | Store | Persistence |
|---|---|---|
| `cookie` | `CookieStore` | client-side, encrypted |
| `redis` | `RedisSessionStore` | `SESSION_REDIS_URL` |
| `database` | `DatabaseSessionStore` | `SESSION_DATABASE_URL` (persistent) |
| `file` | `FileSessionStore` | `SESSION_FILES_PATH` |

`SessionConfig.driver` is a `SessionDriver` `StrEnum` (parity with `CacheDriver`), so an unknown `SESSION_DRIVER` fails at config validation rather than deep inside `SessionManager.store()`.

## Cookie store always encrypts

`CookieStore` uses an AES-256-GCM + HMAC-SHA256 envelope, with enc/mac keys derived from `app_key` (`SESSION_SECRET_KEY`) via HKDF.

> **Note**: The cookie store **always** encrypts. `SESSION_ENCRYPT` only governs the cookie driver here; the server-side stores (`redis`/`database`/`file`) persist JSON payloads, so put them behind a private network or encrypted backend rather than relying on this flag.

## Middleware

`StartSession` parses the cookie, reads the store, attaches `SessionData` to `scope["state"]["session"]`, and writes back on the final response chunk. The `Set-Cookie` header is built from the middleware's config:

```python
from arvel.config.session_config import SameSite
from arvel.session.middleware import SessionCookie, StartSession

StartSession(app, store, SessionCookie(lifetime=7200, secure=False, same_site=SameSite.LAX))
# -> arvel_session=...; Max-Age=7200; Path=/; HttpOnly; SameSite=Lax
# secure=True appends "; Secure"; same_site=SameSite.NONE forces Secure on.
```

The cookie knobs are bundled in a `SessionCookie` options object (sourced from `SESSION_*`). The cookie is always `HttpOnly`. `SameSite` is a `StrEnum` (`LAX`/`STRICT`/`NONE`); `SessionConfig.same_site` coerces the `SESSION_SAME_SITE` string case-insensitively, falling back to `LAX` for anything unrecognized, and `NONE` forces `Secure` on since browsers reject `SameSite=None` without it.

## Provider

`SessionServiceProvider.register()` builds the manager and binds the `Session` facade; `boot()` publishes the sessions migration. The middleware is **not** auto-mounted — add `StartSession` to a middleware group yourself.

## See also

- [Auth](auth.md) — `SessionGuard` reads `_auth_id` from the session.
- [Middleware](../http/middleware.md)
