# Facades

Throughout the Arvel documentation, you'll see references to `Route`, `Cache`, `DB`, `Mail`, `Bus`, `Event`, `Notification`, `Config`, and `Auth`. These are **facades** — static-like proxies that resolve their underlying service from the [Service Container](container.md) on every access.

If you've used Laravel, this is the same concept. The implementation differs because Python doesn't have PHP's facade trick — Arvel uses regular classes whose class methods (and `__class_getitem__`) delegate to a container-resolved instance.

## Why facades?

Facades give you a concise, typed entry point that doesn't require dependency injection at every call site:

```python
from arvel.facades import Cache, DB, Mail


# Without facades: dependency-injected
@Route.get("/users")
async def list_users(
    cache: CacheManager = dep(CacheManager),
    db: Database = dep(Database),
) -> list[dict]:
    cached = await cache.get("users")
    if cached:
        return cached
    users = await db.table("users").get()
    await cache.put("users", users, ttl=60)
    return users


# With facades: zero-ceremony
@Route.get("/users")
async def list_users() -> list[dict]:
    cached = await Cache.get("users")
    if cached:
        return cached
    users = await DB.table("users").get()
    await Cache.put("users", users, ttl=60)
    return users
```

Both are correct. Facades win for readability; explicit injection wins for testability when you need to swap implementations without touching the container.

## How facades work

Each facade is a class with `@classmethod`s that internally do `container.resolve(...)`:

```python
class Cache:
    @classmethod
    async def get(cls, key: str) -> object | None:
        return await container.resolve(CacheManager).get(key)

    @classmethod
    async def put(cls, key: str, value: object, ttl: int | None = None) -> None:
        await container.resolve(CacheManager).put(key, value, ttl)
```

The container that the facade resolves against is **the currently active application's container**. In production, that's set once when `Application.into_asgi()` is called. In tests, you can scope a different container per test via the `with_container` fixture.

## Testability

Because facades are container-resolved, you can swap the binding in a test and the facade picks up the new instance automatically:

```python
def test_cache_uses_array_driver(arvel_app) -> None:
    arvel_app.container.instance(CacheManager, ArrayCacheManager())
    # ...rest of the test uses Cache.* against the fake
```

No monkey-patching, no `import` games. Same code path, different binding.

## Testing with fake()

Several facades expose a `fake()` helper that swaps the backing service with an in-memory recorder. The recorder captures what would have been sent or dispatched without touching the network, SMTP server, or queue broker.

**Mail** — `fake()` returns a context object. Check `.sent` for captured messages:

```python
async def test_welcome_email() -> None:
    driver = Mail.fake()
    await client.post("/signup", json={"email": "a@b.com"})
    assert len(driver.sent) == 1
    assert driver.sent[0].to == "a@b.com"
```

**Event** — after calling `Event.fake()`, use `Event.assert_dispatched()` on the class:

```python
async def test_signup_fires_registered_event() -> None:
    Event.fake()
    await client.post("/signup", json={"email": "a@b.com"})
    Event.assert_dispatched(UserRegistered, times=1)
    Event.assert_not_dispatched(OrderPlaced)
```

**Cache** — `Cache.fake()` is a context manager that swaps to the array driver and provides `assert_stored` / `assert_missing`:

```python
async def test_profile_cached() -> None:
    with Cache.fake():
        await client.get("/profile/1")
        Cache.assert_stored("profile:1")
```

**Storage** — `Storage.fake()` replaces the bound disk with an in-memory fake:

```python
async def test_avatar_upload() -> None:
    with Storage.fake():
        await client.post("/avatar", files={"file": b"..."})
        Storage.assert_exists("avatars/user-1.png")
```

| Facade | `fake()` | Assert helpers |
|---|---|---|
| `Mail` | ✅ | `.sent` list on returned context |
| `Event` | ✅ | `Event.assert_dispatched()`, `Event.assert_not_dispatched()` |
| `Cache` | ✅ | `Cache.assert_stored()`, `Cache.assert_missing()` |
| `Storage` | ✅ | `Storage.assert_exists()`, `Storage.assert_missing()` |
| `Bus` | ❌ | Use per-test `QueueManager` swap |
| `Notification` | ❌ | Use per-test driver swap |
| `DB` | ❌ | Use a per-test transaction rollback fixture |

## The full facade list

| Facade | Underlying service | Provider |
|---|---|---|
| `Route` | `Router` | `HttpServiceProvider` |
| `Config` | `ConfigRegistry` | `ConfigServiceProvider` |
| `Cache` | `CacheManager` | `CacheServiceProvider` |
| `Session` | `SessionManager` | `SessionServiceProvider` |
| `DB` | `Database` | `DatabaseServiceProvider` |
| `Schema` | `SchemaBuilder` | `DatabaseServiceProvider` |
| `Mail` | `Mailer` | `MailServiceProvider` |
| `Notification` | `NotificationDispatcher` | `NotificationServiceProvider` |
| `Bus` | `JobBus` | `QueueServiceProvider` |
| `Event` | `EventDispatcher` | `EventServiceProvider` |
| `Auth` | `AuthManager` | `AuthServiceProvider` |
| `Log` | `Logger` | `LogServiceProvider` |
| `Storage` | `FilesystemManager` | `StorageServiceProvider` |
| `Broadcast` | `BroadcastManager` | `BroadcastServiceProvider` |

## When to skip facades

Use explicit dependency injection (`dep(...)`) instead when:

- A function needs the same service many times — inject once, reuse.
- A function will be unit-tested in isolation without `Application` boot.
- You want the dependency to show up in the function signature for documentation.

Use facades when:

- The dependency is incidental to the function's main job.
- You want minimal ceremony.
- You're writing a handler whose primary inputs come from the request.

Both styles compose fine. Pick per call site.

## Where to next?

- [Service Container](container.md) — what facades resolve through.
- [Service Providers](providers.md) — where facades' bindings come from.
- [Configuration](configuration.md) — the `Config` facade in depth.
