# Cache

<a name="introduction"></a>
## Introduction

Some data retrieval or processing tasks are CPU-intensive or take several seconds. When this is the case, it's common to cache the retrieved data so it can be served quickly on subsequent requests. Arvel provides an expressive, unified API across various cache backends through the `Cache` facade.

> [!NOTE]
> The `Cache` facade covers the common operations: `get`, `put`, `forget`, `has`, `flush`, `forever`, and `remember`. Some Laravel conveniences — `add`, `increment`, `decrement`, `pull`, `remember_forever`, `many`/`put_many` — are **not** on the facade. `many`/`put_many` exist on the store, reachable via `Cache.store().many(...)`.

<a name="configuration"></a>
## Configuration

Cache reads `config/cache.py` — `default` picks the active store and `stores` maps each named store to its settings. The `CACHE_*` environment variables are the fallback when a key isn't in the file (see [the cascade](../core-concepts/configuration.md#the-cascade)). The driver is chosen by `CACHE_CONNECTION` (there is no `CACHE_STORE`); when unset, the cache defaults to the in-memory `array` driver.

```ini
CACHE_CONNECTION=redis
CACHE_HOST=127.0.0.1
CACHE_PORT=6379
CACHE_PREFIX=arvel_cache
```

<a name="drivers"></a>
### Drivers

| Driver | Backing store | Notes |
|---|---|---|
| `array` | In-process dict | Default; not shared across processes |
| `file` | JSON files | `CACHE_FILE_PATH` |
| `redis` | Redis | Requires `arvel[redis]`; supports atomic locks |
| `database` | SQL table | See the warning below |
| `null` | No-op | Disables caching |

> [!WARNING]
> The `database` cache store currently hardcodes an in-memory SQLite URL — it is not yet wired to your application database. Use `redis` or `file` for shared, persistent caching.

> [!NOTE]
> TTLs are always **integer seconds**, not `timedelta`. On `put`, a `None` TTL means "store forever" across every store (matching Laravel, where `Cache::put($key, $val, null)` is equivalent to `forever`). Use a positive TTL to set an expiry.

<a name="registering-the-provider"></a>
### Registering the Provider

The cache is **opt-in**. Add `CacheServiceProvider` to `bootstrap/providers.py` before using the `Cache` facade — otherwise it raises a not-bound error. See [Service Providers](../core-concepts/service-providers.md#opt-in-providers).

<a name="cache-usage"></a>
## Cache Usage

```python
from arvel.facades import Cache
```

<a name="retrieving-items"></a>
### Retrieving Items

```python
value = await Cache.get("key")
value = await Cache.get("key", "default")
exists = await Cache.has("key")
```

<a name="storing-items"></a>
### Storing Items

```python
await Cache.put("key", "value", ttl=60)   # expires in 60 seconds
await Cache.put("key", "value")            # no expiry
await Cache.forever("key", "value")        # explicitly no expiry
```

<a name="remember"></a>
### Remember

`remember` returns a cached value if present, otherwise runs the callback, stores the result, and returns it. The callback must be **async**:

```python
async def compute() -> dict[str, int]:
    # expensive work you don't want to repeat on every request
    return {"total": await Order.query().count()}

stats = await Cache.remember("order_stats", ttl=300, callback=compute)
```

`Order` here is one of your own models; `compute` runs only on a cache miss.

<a name="removing-items"></a>
### Removing Items

```python
await Cache.forget("key")
await Cache.flush()           # clear the entire store
```

<a name="cache-tags"></a>
## Cache Tags

Tags let you store related items under a namespace and invalidate them together in O(1). The tagged cache supports `put`, `get`, `forget`, and `flush`:

```python
await Cache.tags(["posts"]).put("post:1", {"title": "Hello"}, ttl=60)
value = await Cache.tags(["posts"]).get("post:1")
await Cache.tags(["posts"]).flush()    # invalidate everything tagged "posts"
```

<a name="atomic-locks"></a>
## Atomic Locks

Atomic locks coordinate work across processes — useful for preventing duplicate jobs. Acquire a lock as an async context manager:

```python
lock = Cache.lock("reports:generate", ttl=60)

async with lock as acquired:
    if acquired:
        await generate_report()
```

Or manage it manually with `acquire`, `release`, `extend`, and `block` (wait up to a timeout).

> [!WARNING]
> Truly atomic, cross-process locking requires the **Redis** store, which implements it with a Lua script. Other stores fall back to a process-local lock and emit a warning — fine for single-process use, not for distributed coordination.

<a name="rate-limiting"></a>
## Rate Limiting

The cache exposes a rate limiter for throttling actions:

```python
limiter = Cache.rate_limiter()

if await limiter.attempt("send-mail:user:1", max_attempts=5, decay=60):
    await send_mail()
else:
    remaining = await limiter.remaining("send-mail:user:1", max_attempts=5)
```

<a name="testing"></a>
## Testing

`Cache.fake()` swaps in an array-backed store and adds assertions:

```python
with Cache.fake():
    await Cache.put("k", "v", ttl=60)
    Cache.assert_stored("k")
    Cache.assert_missing("other")
```
