# WI-arvel-034 — Cache RateLimiter must use a fixed window, not a sliding TTL

- **Module**: 34 — cache rate limiter (`cache/rate_limiter.py`, the `Cache.rate_limiter()` facade)
- **Complexity**: L2
- **Risk tier**: 2 (correctness/parity on a throttling primitive; not a direct bypass)
- **Data classification**: internal
- **Status**: completed

## Problem

`RateLimiter.attempt` reset the cache TTL on **every** hit:

```python
await self._store.put(counter_key, int(count) + 1, ttl=decay)  # fresh decay each time
```

So the window slid forward with traffic instead of being anchored to the first
hit. The docstring claimed the opposite — "The counter resets after `decay`
seconds from the **first** hit within the window" — so the code contradicted its
own contract, and diverged from Laravel's `RateLimiter`, which uses a fixed
window (`Cache::add` for the TTL, then atomic `increment` that never touches it).

Observable effect: a client making steady allowed requests keeps the counter
alive indefinitely; once it reaches the cap it stays capped for `decay` seconds
measured from the *last* allowed hit, not the first. `remaining()` never recovers
while traffic continues.

## Repro

```python
limiter = Cache.rate_limiter()
# max_attempts=2, decay=60, first hit at t=1000 (window -> 1060)
await limiter.attempt(key, 2, 60)        # t=1000 -> True
await limiter.attempt(key, 2, 60)        # t=1040 -> True (old code: window slides to 1100)
await limiter.attempt(key, 2, 60)        # t=1050 -> False (capped)
await limiter.attempt(key, 2, 60)        # t=1061 -> should be True (window elapsed)
# old (sliding) code: still False at t=1061, because t=1040 pushed the window to 1100
```

## Fix

Store the window as `{"hits": int, "reset_at": epoch}` and preserve the original
expiry — increments use only the *remaining* TTL, never a fresh `decay`:

```python
window = _window(await self._store.get(counter_key), now)
if window is None:                       # absent or elapsed -> new window
    await self._store.put(counter_key, {"hits": 1, "reset_at": now + decay}, ttl=decay)
    return True
hits, reset_at = window
if hits >= max_attempts:
    return False
remaining_ttl = max(int(reset_at - now), 1)
await self._store.put(counter_key, {"hits": hits + 1, "reset_at": reset_at}, ttl=remaining_ttl)
```

`_window` is a typed helper that returns `(hits, reset_at)` for a live window or
`None` when the record is missing/expired; `remaining()` shares it. The value
shape is a plain dict so it round-trips through every cache store (array, file,
database, redis).

## Acceptance criteria

- The window is anchored to the first hit; in-window hits don't extend it.
- After the window elapses, the next attempt starts a fresh window and
  `remaining()` returns `max_attempts` again.
- Existing attempt/remaining/reset semantics unchanged within a window.
- ruff + format, mypy, pyright clean; cache + throttle + auth suites green.

## Out of scope (documented limitation, not fixed)

- **Cross-process atomicity.** The read-modify-write (`get` then `put`) isn't
  atomic — the `CacheStore` protocol has no atomic `increment`/`add`, mirroring
  the documented process-local caveat on `Cache.lock()` and `remember()`. Under
  heavy concurrency a few requests can slip past the cap. For distributed,
  race-free throttling the framework already ships the `Throttle` middleware,
  whose `RedisStore` counts with an atomic `INCR` (fixed window via `EXPIRE` on
  first hit). Documented in `features/cache.md`.

## Files

- `packages/arvel/src/arvel/cache/rate_limiter.py`
- `packages/arvel/tests/cache/test_rate_limiter.py` (2 new window cases)
- `docs/site/docs/features/cache.md` (fixed-window + concurrency note)

## Notes

Pre-existing, unrelated suite failure out of scope: `tests/observability/test_wi_030_config.py`
(cwd-dependent skeleton path, flagged since WI-arvel-030).
