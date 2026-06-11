# Cache

`CacheManager` selects a store from config and exposes get/put/remember plus tagged caches, locks, and a rate limiter.

**Source**: `packages/arvel/src/arvel/cache/` — `__init__.py` (`CacheManager`), `store.py`, `locks.py`, `providers/` (`providers/cache_provider.py`), `config/cache_config.py`.

## Manager and stores

```mermaid
flowchart LR
    Cache["Cache facade"] --> CM["CacheManager"]
    CM -->|store(driver)| S{store}
    S --> Arr["array (in-process dict)"]
    S --> File["file (JSON per key)"]
    S --> Null["null (no-op)"]
    S --> Redis["redis"]
    S --> DBs["database (app DB connection)"]
```

Stores implement a `CacheStore` protocol (`put`/`get`/`forget`/`has`/`flush`/`forever`/`many`/`put_many`). `ttl=None` means forever. `CacheManager` lazily builds and caches one store per driver.

The driver comes from `CacheConfig` (`CACHE_*`, default `array`):

| Driver | Backing | Notes |
|---|---|---|
| `array` | process dict | monotonic TTL |
| `file` | files (SHA-256 names) | JSON per key |
| `null` | nothing | no-op |
| `redis` | `redis.asyncio` | `setex`/`set` |
| `database` | app DB connection | `cache_entries` table |

The `database` store shares the application's default DB connection via `DB.session_maker_for()`, so cached values persist across processes and survive restarts. Publish and run the cache migration (`vendor:publish --tag=arvel-cache`, then `arvel migrate`) to create the `cache_entries` table before selecting this driver.

## Locks

```python
class CacheLock:
    async def acquire(self) -> bool: ...
    async def release(self) -> None: ...
    async def block(self, timeout=0, *, backoff=0.05, max_backoff=1.0) -> bool: ...
    async def __aenter__(self) -> bool: ...
```

- **Redis** — `acquire_lock`/`release_lock`/`extend_lock` use `SET NX` + Lua: true distributed atomic locks.
- **Anything else** — falls back to a per-key `asyncio.Lock` + `has()`/`put()`, which is process-local only. `CacheManager.lock()` emits a `RuntimeWarning` when the store isn't an `AtomicLockStore`.

> **Warning**: Cross-process atomic locks (`onOneServer`, `withoutOverlapping`) only work on the Redis store.

## Provider

`CacheServiceProvider.register()` builds the manager and binds the `Cache` facade. `boot()` publishes the cache migration stub and registers a `CacheService` health probe (put/get round-trip).

## See also

- [Scheduling](scheduling.md) — overlap/one-server locks use the cache.
- [Configuration](../architecture/ARCH-006-configuration.md)
