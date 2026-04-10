# Cache

Caching is how you survive traffic spikes without hammering the database on every request. Arvel treats caching as a **contract** (`CacheContract`) with multiple drivers, the same way Laravel swaps `redis`, `file`, or `array` behind a single facade-like surface in the container.

At **v0.1.0**, configuration flows through **`CacheSettings`**: prefix, default TTL, Redis URL, and driver name—all overridable with `CACHE_*` environment variables.

## The contract

`CacheContract` defines the async operations your application code should depend on:

- **`get` / `put` / `forget` / `has`** — the usual key/value lifecycle
- **`flush`** — clear the configured store (use with care)
- **`remember`** — get from cache or run an async callback and store the result

Implementations in the framework include **memory** (great for tests and local dev), **Redis** (production-friendly), and **null** (a no-op that never persists—handy for dry runs).

## Configuration

`CacheSettings` lives beside the rest of your module settings. Typical fields:

- **`driver`** — `"memory"`, `"redis"`, or `"null"`
- **`prefix`** — namespaces keys when you share a Redis instance
- **`default_ttl`** — seconds, used when callers omit TTL
- **`redis_url`** — connection string for the Redis driver

You set these via environment variables (`CACHE_DRIVER`, `CACHE_REDIS_URL`, etc.) or your config layer—whatever your app’s bootstrap prefers.

## Using the cache in application code

Resolve `CacheContract` from the container (pattern depends on your app package) and call async methods:

```python
from arvel.cache.contracts import CacheContract


async def expensive_stats(cache: CacheContract) -> dict[str, int]:
    return await cache.remember(
        "dashboard.stats",
        ttl=300,
        callback=_compute_stats,
    )


async def _compute_stats() -> dict[str, int]:
    # Hit the DB once, then serve from cache for five minutes
    return {"users": 42, "orders": 7}
```

## Mental model

Think “Laravel cache store,” but **async-first** and **typed**: your services take `CacheContract`, tests swap in memory or null, and production runs Redis without changing call sites. If you need to invalidate after a write, call `forget` for the keys you own—Arvel does not guess your domain’s consistency rules.

That separation—**contract in code, driver in config**—is what keeps cache from becoming a hidden global.
