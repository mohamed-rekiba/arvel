# Cache

Some work is expensive and rarely changes — a dashboard aggregate, a slow third-party API response,
a rendered fragment. Recomputing it on every request is pure waste. A cache lets you compute once and
serve the result from a fast key/value store until it's worth recomputing.

arvel's cache is an async store over [cashews](https://github.com/Krukov/cashews), with the backend
selectable by config. This page covers the basic get/put API, the `remember` compute-or-fetch
helper, the `@cached` decorator, choosing a backend, and atomic locks.

!!! note "Backends"
    The in-process `array` driver is the default and needs nothing — great for one instance and for
    tests. A cache that's **shared across instances and survives restarts** needs Redis:
    `uv add 'arvel[redis]'`, then set `cache.default = "redis"`.

## Basic usage

```python
from arvel.support import cache       # the global helper → the default driver

await cache().put("answer", 42, ttl=600)   # store for 10 minutes
await cache().get("answer")                # 42
await cache().get("missing", default=0)    # 0
await cache().forget("answer")             # delete
```

`cache()` mirrors `config()` — it returns the default cache driver, so you never hand-build
`CacheManager().driver()`. (It lives in `arvel.support`, not `arvel`, because the bare name
`arvel.cache` is the cache *package*.)

## Remember

`remember` returns the cached value if present, otherwise runs the callback, caches its
result, and returns it — the single most useful cache pattern:

```python
async def expensive() -> list[dict]:
    return await db.select("SELECT * FROM report")

rows = await cache().remember("daily-report", ttl=3600, callback=expensive)
```

Use `remember_forever` to cache without expiry:

```python
settings = await cache().remember_forever("app-settings", load_settings)
```

## Memoize a function with `@cached`

To cache an **async function's** result keyed by its arguments, decorate it:

```python
from arvel import cached

@cached(ttl=300)
async def top_posts(limit: int):
    return await Post.where(published=True).order_by("-views").limit(limit).get()
```

The first call computes and stores; later calls with the same args return the cached value (a
cached `None` is remembered too, not recomputed). Pass `key="…"` to fix the cache key, or use bare
`@cached` for forever.

## Choosing a backend

The active driver comes from `cache.default` in config (defaults to `array`, the in-memory
store, which needs no extras). Redis is enabled by installing the `[redis]` tier and setting
`cache.url` to your Redis URL.

## Atomic locks

A lock prevents two workers from doing the same work at once (e.g. regenerating a report). It's
an async context manager over the cache backend:

```python
cache = CacheManager().driver()

async with cache.lock("report:daily", ttl=60):
    await regenerate_report()        # only one holder runs this at a time
```

The TTL bounds how long the lock is held even if the holder crashes, so a dead process can't
wedge it forever.

## Worked example: cache-aside in a handler

```python
async def dashboard(request):
    stats = await cache().remember(f"stats:{request.user().id}", ttl=300, callback=compute_stats)
    return {"stats": stats}
```

## Common mistakes & gotchas

- **`remember` with a per-user key but a shared name.** Key by what varies (`stats:{user_id}`),
  or one user sees another's cached value.
- **Caching `None` ambiguously.** `get(key)` returns the default (`None`) for a miss *and* for a
  stored `None` — pass a sentinel default if you must tell them apart.
- **No TTL on volatile data.** `put` without `ttl` keeps the value until evicted/forgotten; set a
  TTL for anything that goes stale, and use a lock around expensive regeneration to avoid a
  stampede when it expires.
- **Expecting `array` to persist.** The in-memory store is per-process and cleared on restart —
  use Redis for anything shared across workers or restarts.

## How it works

`Cache` is a facade over a `CacheManager` (a driver manager); `driver()` resolves the configured
backend and caches the `CacheRepository` wrapping a real `cashews.Cache`. `remember` is
get-or-set: a hit returns immediately, a miss runs the callback, stores the result under the
TTL, and returns it. Locks delegate to cashews' backend lock. cashews is imported lazily, so
`import arvel` stays light until you touch the cache.

## See also

- [Queues & Jobs](queues.md) — cache a job's expensive lookups.
- [About arvel](about.md) — the cashews engine behind the cache.
