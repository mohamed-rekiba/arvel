# ADR-102: `CacheVersioner` — Version-stamp invalidation without flush

**Status**: Accepted
**Date**: 2026-05-24

## Context

The e-commerce demo's `ItemService` and the fullstack Vue demo needed a pattern to
invalidate list caches without calling `Cache.flush()`, which would evict rate-limit
counters, session data, and unrelated cached entries from the same store.

## Decision

Ship `CacheVersioner` in `arvel.cache.versioner` with the following contract:

```python
versioner = CacheVersioner("items:list", store=cache_store)
key = await versioner.versioned_key("user:1", "page:2")   # unique per version
await versioner.invalidate()                               # bumps version counter
```

`versioned_key(*parts)` returns `{namespace}:{parts_hash}:v{version}`. When `invalidate()`
increments the version counter, all old keys become unreachable — they expire via TTL
without an explicit delete. `Cache.flush()` is never called.

Version counters are stored under namespaced keys to prevent collisions:
`__arvel_versioner__:{namespace}:v`.

## Rationale

- **No flush**: `Cache.flush()` clears the entire store — not acceptable in shared-store
  deployments where rate-limiters and sessions live alongside list caches.
- **Namespace isolation**: Without namespacing, two `CacheVersioner` instances for
  different resource types could collide on version counter keys.
- **TTL-based GC**: Old versioned keys expire naturally — no background cleanup job needed.
- **`arvel.cache` placement**: Cache utilities belong in the cache module. No cross-module
  imports.

## Rejected Alternatives

- `Cache.delete()` on every list key: requires tracking which keys exist — error-prone
  under concurrent writes and across multiple app instances.
- `Cache.tags()` (if supported): not all cache drivers support tag-based invalidation;
  `CacheVersioner` works on any driver.
