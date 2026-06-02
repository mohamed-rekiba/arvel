# Session

`SessionManager` selects a store; `StartSession` middleware reads the cookie, attaches session data to the request, and writes it back on response.

**Source**: `packages/arvel/src/arvel/session/` — `manager.py`, `store.py`, `stores/`, `middleware.py`, `providers/`, `config/session_config.py`.

## Stores

```python
class SessionStore(Protocol):
    async def read(self, session_id) -> dict[str, Any]: ...
    async def write(self, session_id, data, lifetime) -> None: ...
    async def destroy(self, session_id) -> None: ...
    async def gc(self, max_lifetime) -> int: ...
```

Driver from `SessionConfig` (`SESSION_*`, default `cookie`):

| Driver | Store | Persistence |
|---|---|---|
| `cookie` | `CookieStore` | client-side, encrypted |
| `redis` | `RedisSessionStore` | `SESSION_REDIS_URL` |
| `database` | `DatabaseSessionStore` | `SESSION_DATABASE_URL` (persistent) |
| `file` | `FileSessionStore` | `SESSION_FILES_PATH` |

## Cookie store always encrypts

`CookieStore` uses an AES-256-GCM + HMAC-SHA256 envelope, with enc/mac keys derived from `app_key` (`SESSION_SECRET_KEY`) via HKDF.

> **Warning**: `SESSION_ENCRYPT` exists on the config but is never read — the cookie store **always** encrypts.

## Middleware

```python
# the Set-Cookie header is hardcoded:
cookie_value = (f"{name}={session_id}; Max-Age={lifetime}; "
                f"Path=/; HttpOnly; SameSite=Lax")
```

`StartSession` parses the cookie, reads the store, attaches `SessionData` to `scope["state"]["session"]`, and writes back on the final response chunk.

> **Warning**: The cookie is always `HttpOnly` with `SameSite=Lax`. `SESSION_SECURE` and `SESSION_SAME_SITE` on the config are **not** applied by `StartSession`. `TODO/QUESTION:` Should the middleware honor `SESSION_SECURE`/`SESSION_SAME_SITE` (e.g. add `Secure` in production)?

## Provider

`SessionServiceProvider.register()` builds the manager and binds the `Session` facade; `boot()` publishes the sessions migration. The middleware is **not** auto-mounted — add `StartSession` to a middleware group yourself.

## See also

- [Auth](auth.md) — `SessionGuard` reads `_auth_id` from the session.
- [Middleware](../http/middleware.md)
