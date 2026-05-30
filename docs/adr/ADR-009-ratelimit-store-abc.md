# ADR-009 — Rate-limit store is an ABC with InMemory + Redis drivers, container-resolved

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.http.ratelimit`

---

## Context

`Throttle` middleware needs a place to record attempt counts per key. Choices:

1. Hard-code in-memory storage. Simple, wrong in production.
2. Hard-code Redis storage. Forces a Redis dependency even on dev/test.
3. ABC + pluggable drivers, container-resolved at runtime.

## Decision

Adopt option 3.

```python
class RateLimiterStore(Protocol):
    async def hit(self, key: str, decay_seconds: int) -> Attempt: ...

class Attempt(NamedTuple):
    count: int
    reset_at: datetime
```

Two built-in drivers:
- `InMemoryStore` — process-local dict + lock; default. Logs a warning at boot if `environment != "local"` and no other store is bound.
- `RedisStore` — uses a Redis connection from the container. Available when `arvel[redis]` is installed (`redis>=5.2` from foundations extras).

`HttpServiceProvider.register()`:
- If `arvel.redis.Redis` is bound to the container AND env var `RATE_LIMIT_STORE == "redis"`, bind `RedisStore`.
- Otherwise bind `InMemoryStore`.

User can override via their own provider.

## Why ABC

- Lets test code use a `FakeStore` without touching Redis.
- Lets enterprise users plug in Memcached or DynamoDB drivers later.
- Avoids the `cache:rate-limit-store-driver=foo` Laravel-ism — Python's container makes the swap declarative.

## Why not just "use the Cache manager"

E5 will introduce `Cache` with its own manager and drivers (Laravel parity). The Throttle middleware could in theory dispatch through Cache. We don't do that now because:
- Cache doesn't exist yet (WI-005).
- Coupling Throttle to Cache means Throttle can't ship until E5, which violates the FAT slice scope.
- Once Cache lands, `RedisStore` will be re-implemented as a thin adapter on top of the Cache driver — the public API (`RateLimiterStore` Protocol) doesn't change.

## Consequences

- One new public type per driver. `RateLimiterStore` is the Protocol; concrete drivers are subclasses.
- The `hit()` method is async — supports both sync (in-memory) and async (Redis) backends uniformly.
- The boot-time warning is a `RuntimeWarning` not an error — production users without rate limiting still boot; they just see a flag.

---

## Cross-references

- PRD-002: FR-002-015, FR-002-016
- SAD-002 §3 (Throttle / Rate limiting component)
- ADR-008 (middleware tier — Throttle is route-level Pipeline)
