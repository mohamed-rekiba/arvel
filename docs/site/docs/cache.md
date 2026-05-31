# Cache

Arvel provides an expressive, unified API for cache backends. The same code reads and writes regardless of whether the underlying store is in-memory, the filesystem, Redis, or the database.

## Configuration

```env
CACHE_DRIVER=redis
CACHE_PREFIX=myapp
CACHE_DEFAULT_TTL=300

REDIS_URL=redis://localhost:6379/0
```

| Driver | Best for | Notes |
|---|---|---|
| `array` | Tests | In-process; cleared on restart |
| `file` | Single-host dev | Filesystem under `storage/cache/` |
| `redis` | Production | Requires `arvel[redis]` |
| `database` | Production without Redis | Slower; uses your DB |

## Basic usage

```python
from arvel.facades import Cache


await Cache.put("user.42.profile", profile, ttl=300)
profile = await Cache.get("user.42.profile")
await Cache.forget("user.42.profile")
```

The full API:

```python
Cache.get(key, default=None)
Cache.put(key, value, ttl=None)
Cache.add(key, value, ttl=None)        # only if not present
Cache.forever(key, value)
Cache.has(key)                         # True if cached — correct even when value is 0, False, or ""
Cache.forget(key)
Cache.flush()                          # clear the whole store
Cache.remember(key, ttl, callback)     # get-or-compute
Cache.increment(key, by=1)
Cache.decrement(key, by=1)
```

## Get-or-compute

The common pattern of "return the cached value or compute and store it":

```python
async def get_dashboard_stats() -> dict:
    return await Cache.remember(
        "dashboard.stats",
        ttl=60,
        callback=lambda: compute_stats(),
    )
```

`remember()` ensures only one in-flight callback per key — even under concurrency — so a cache miss doesn't trigger a thundering herd.

For values that should never expire:

```python
return await Cache.remember_forever("schema_version", load_schema_version)
```

## Tags (Redis only)

When using Redis, group cache entries by tag for bulk invalidation:

```python
await Cache.tags("users", "profiles").put("user.42", profile)
await Cache.tags("users").flush()   # invalidates everything tagged "users"
```

## Lock helpers

Distributed locks for one-shot operations:

```python
async with Cache.lock("send-daily-digest", ttl=300):
    await send_digest()
```

Locks are **atomic** — the check and the claim happen in a single operation, so two concurrent callers can't both acquire the same lock. If another coroutine or process tries to acquire the same lock while it's held, the `async with` blocks until the lock is released or the TTL expires.

To check whether you got the lock without blocking:

```python
async with Cache.lock("heavy-import", ttl=120) as acquired:
    if acquired:
        await run_import()
    # else: another worker is already running it, skip
```

### Extending a held lock

Long-running jobs can renew their lock so it doesn't expire mid-flight. `extend()` resets the
TTL **only if you still own the lock** — a different owner gets `False` and the lock is left
untouched.

```python
lock = Cache.lock("nightly-rollup", ttl=60)
if await lock.acquire():
    try:
        while more_batches():
            await process_batch()
            await lock.extend(60)   # push the expiry out another minute
    finally:
        await lock.release()
```

### Blocking with backoff

`block()` waits for a held lock with exponential backoff so you don't hammer the store under
contention. Retry intervals grow from `backoff`, doubling up to `max_backoff`:

```python
lock = Cache.lock("report", ttl=120)
if await lock.block(timeout=10, backoff=0.1, max_backoff=2.0):
    await build_report()
```

### Distributed semantics

Only the Redis store provides true distributed locks. The array, file, and database stores
fall back to **process-local** locks and emit a `RuntimeWarning` when you call `lock()` — fine
for single-process dev, but use Redis when multiple workers must coordinate.

### Testing locks

`LockFake` is a drop-in double with assertion helpers:

```python
from arvel.testing.fakes import LockFake

fake = LockFake("job:import")
await fake.acquire()
fake.assert_acquired("job:import")

fake = LockFake("job:import", succeeds=False)
await fake.acquire()
fake.assert_nothing_acquired()
```

## Choosing a key naming convention

Arvel doesn't enforce a key format, but consistency matters when you debug cache misses. A useful convention:

```
<entity>.<id>.<aspect>      → "user.42.profile"
<aggregate>.<key>           → "dashboard.stats"
<scope>:<query-hash>        → "users:search:abc123def"
```

Avoid putting user-controlled data directly in keys without hashing — long or malformed keys can hit driver limits.

## Cache vs session vs storage

| Use case | Layer |
|---|---|
| Expensive computation result | **Cache** |
| Per-user state across requests | **Session** |
| File uploads, generated artifacts | **Storage** |

If it's expendable, use Cache. If it's user-bound, use Session. If it's a file, use Storage.

## Versioned cache invalidation

`CacheVersioner` solves "how do I invalidate all cached queries for a user?" without needing tag support or cache flushing. Each versioner holds a version counter in the cache store. Keys generated from it include the current version, so bumping the version makes every previously generated key stale.

```python
from arvel.cache import CacheVersioner


items_versioner = CacheVersioner("items:list", store=Cache.store())

# Build a key scoped to user + page
key = await items_versioner.versioned_key("user:42", "page:1")
# → "items:list:v3:user:42:page:1"

await Cache.remember(key, ttl=300, callback=lambda: fetch_items(42, page=1))

# When the user mutates their items, invalidate everything at once
await items_versioner.invalidate()

# The next call to versioned_key returns a new version
key = await items_versioner.versioned_key("user:42", "page:1")
# → "items:list:v4:user:42:page:1"  (cache miss → fresh data)
```

Each `CacheVersioner` is scoped to its prefix. Invalidating `items:list` doesn't affect `users:list`.

## Where to next?

- [Session](session.md) — for per-user state.
- [File Storage](filesystem.md) — for files.
- [Rate Limiting](rate-limiting.md) — uses cache as the backing store.
