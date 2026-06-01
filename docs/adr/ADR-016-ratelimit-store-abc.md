# ADR-016 — Rate-limit store is a Protocol with InMemory + Redis drivers, container-resolved

**Date**: 2026-05-17
**Status**: Accepted (interface reconciled — Protocol, not ABC)
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.http.ratelimit`

---

## Context

The `Throttle` middleware needs to record attempt counts per key. Options: hard-code in-memory (simple, wrong in production); hard-code Redis (forces a Redis dependency in dev/test); or a pluggable store interface resolved through the container.

## Decision

**Pluggable store interface, container-resolved.** The store contract is a `typing.Protocol` (consistent with ADR-077), not an ABC:

```python
@runtime_checkable
class RateLimiterStore(Protocol):
    async def hit(self, key: str, *, decay_seconds: int) -> Attempt: ...

@dataclass(frozen=True, slots=True)
class Attempt:
    count: int
    reset_at: datetime
```

Two built-in drivers:
- `InMemoryStore` — process-local dict + `asyncio.Lock`. The default binding.
- `RedisStore` — wraps a Redis client (lazy import; needs `arvel[redis]`). Hashes keys (SHA-256) and uses `INCR` + `EXPIRE`; tolerates sync or async client methods.

`HttpServiceProvider.register()` binds `RateLimiterStore → InMemoryStore` by default. Users swap to Redis (or any custom store) by binding their own implementation of the Protocol in a provider.

## Why a Protocol

- Tests use a fake store without touching Redis.
- Enterprise users plug in Memcached/DynamoDB drivers later.
- Container binding makes the swap declarative — no Laravel-style string driver config.

`Throttle` is not coupled to the Cache subsystem: the `hit()` method is async so both sync (in-memory) and async (Redis) backends present one uniform interface.

## Consequences

- One public type per driver; `RateLimiterStore` is the Protocol.
- `decay_seconds` is keyword-only; `Attempt` is an immutable dataclass carrying the current `count` and `reset_at`.

## Current implementation

- Code: `packages/arvel/src/arvel/http/ratelimit.py`; default binding in `packages/arvel/src/arvel/providers/http_provider.py`.
- Docs: `docs-fresh/http/middleware.md`.

## Notes

- **Reconciled from the original**: the title and body said "ABC"; the shipped contract is a `Protocol`. The earlier draft also described a `RATE_LIMIT_STORE` env var, automatic Redis binding, and a boot-time `RuntimeWarning` for non-local environments — **none of that is implemented**. The provider binds `InMemoryStore`; Redis is opt-in by binding it yourself. The `redis>=5.2` floor referenced in the original is now `redis>=7.4` (see ADR-004 extras).
