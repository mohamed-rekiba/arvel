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
await cache().has("answer")                # True — tests presence, so a stored None still counts
await cache().forget("answer")             # delete
```

`has()` reports whether the key exists, not whether its value is truthy: after `put("k", None)`,
`has("k")` is `True`. Use it to tell a cached `None` apart from a miss (`get` with a default can't).

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

## More verbs: add, pull, forever, touch, decrement

```python
await cache().add("lock:seeded", True, ttl=60)      # True first time, False while present
await cache().pull("flash-message")                 # get, then delete, in one call
await cache().forever("app-settings", settings)     # store with no expiry
await cache().touch("session:abc", 1800)             # refresh a key's TTL (alias of `expire`)
await cache().decrement("stock:sku-1", 3)            # mirrors `increment`
```

`add` is **atomic** — on Redis it's a single `SET NX`, so concurrent callers racing to seed the
same key never both "win" (`Cache::add` parity).

## Stale-while-revalidate with `flexible`

`flexible` serves a cached value immediately, but recomputes it in the *background* once it's a
little stale — callers never wait on the recompute unless the value is old enough to be unusable:

```python
posts = await cache().flexible(
    "top-posts",
    (60, 3600),          # fresh for 60s; stale-but-servable for up to 1h
    load_top_posts,
)
```

- **Within 60s** of the last compute: serves the cached value.
- **Between 60s and 1h**: serves the (stale) cached value immediately, and fires a single
  background recompute (concurrent stale hits during this window all get served the same stale
  value — only one of them actually triggers a recompute).
- **Past 1h**, or on a miss: recomputes inline and waits for the result.

## Atomic locks

A lock prevents two workers from doing the same work at once (e.g. regenerating a report).
`lock()` returns a `CacheLock` with an owner token (`secrets.token_hex`, unique per handle) — only
the holder that acquired it can release it:

```python
cache = CacheManager().driver()

async with cache.lock("report:daily", seconds=60):
    await regenerate_report()        # only one holder runs this at a time; raises
                                      # LockAcquireFailed immediately if already held
```

`async with lock:` tries **once** and raises `LockAcquireFailed` if the lock is already held — to
wait instead, use `block`:

```python
lock = cache.lock("report:daily", seconds=60)
try:
    await lock.block(wait_seconds=5)   # retries until acquired or LockTimeout
    await regenerate_report()
finally:
    await lock.release()               # no-ops if this handle doesn't own it anymore
```

- `force_release()` frees the lock unconditionally, regardless of owner (an operator's escape
  hatch for a wedged lock).
- `restore_lock(name, owner)` recreates a lock handle from a stored owner token — release a lock
  from a different process/instance than the one that acquired it.
- The `seconds` TTL bounds how long the lock is held even if the holder crashes, so a dead process
  can't wedge it forever.

## Tags

Tag related cache entries so they can be invalidated together — a plain `flush()` clears
*everything*, but tags scope that down:

```python
await cache().tags("people", "artists").put("user:1:profile", profile, ttl=3600)
await cache().tags("people", "artists").get("user:1:profile")   # visible through these tags
await cache().get("user:1:profile")                              # None — untagged read misses it

await cache().tags("people").flush()   # removes every entry ever tagged "people"
```

An entry written through a tag combination is readable **only** through that same combination;
flushing a single tag removes every entry ever written with it, even via a different combination
(so `tags("people", "artists")->flush()`'s *only* tag, "people", also invalidates it).

## The Redis facade

For direct Redis access — commands, pipelines, pub/sub — beyond what the cache abstraction
offers, use the `Redis` facade (needs the `[redis]` extra, same as the `redis` cache driver):

```python
from arvel.support.facades import Redis

await Redis.command("SET", "greeting", "hi")
await Redis.command("GET", "greeting")                    # b"hi"

async with Redis.pipeline() as pipe:                       # batch N ops in one round trip
    pipe.command("INCR", "views").command("INCR", "likes")
    incremented_views, incremented_likes = await pipe.execute()

await Redis.publish("orders", "order.created:42")
async for message in Redis.subscribe("orders"):
    print(message)                                         # yields each published message
    break

await Redis.eval("return redis.call('GET', KEYS[1])", keys=["greeting"])
```

Configure the connection via the `redis` config section (`redis.url` for the default connection,
`redis.connections.{name}.url` for additional named ones); `Redis.connection("reporting")`
resolves a named connection.

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
TTL, and returns it. `add` uses cashews' atomic `set(..., exist=False)` (a single `SET NX` on
Redis). `flexible` stores `(value, stored_at)` and fires its background revalidation via
`asyncio.create_task`, single-flight-guarded by `add()` so concurrent stale hits refresh once.

Locks are `arvel`'s own `CacheLock` (**not** cashews' built-in lock, which lacks owner
semantics): Redis acquires with a raw `SET NX PX` and releases with a Lua compare-and-delete
script (atomic across processes); the array driver uses a plain in-process dict (no `await`
between its check and its write, so nothing else can interleave). Tags key entries by their
sorted tag-name combination and track membership per tag via cashews' generic `set_add`/
`set_pop` commands — works identically on both drivers, so `flush()` doesn't need driver-specific
code. cashews (and `redis.asyncio`, for the `Redis` facade) are imported lazily, so `import arvel`
stays light until you actually touch the cache or Redis.

## See also

- [Queues & Jobs](queues.md) — cache a job's expensive lookups.
- [About arvel](about.md) — the cashews engine behind the cache.
