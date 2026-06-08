# Epic: Cache RateLimiter uses a fixed window, matching Laravel

## Summary
`Cache.rate_limiter().attempt()` must anchor its window to the first hit and let
it expire `decay` seconds later, instead of resetting the TTL on every hit (a
sliding window that contradicted the docstring and Laravel's `RateLimiter`).

**Module:** cache · **Spec:** `docs/pipeline/specs/WI-arvel-034-rate-limiter-fixed-window.md`

## Stories

### Story 1: Fixed window anchored to the first hit
**As a** developer throttling an action with `Cache.rate_limiter()`, **I want** the
window to reset `decay` seconds after the first hit, **so that** the limit behaves
predictably and matches Laravel — not a window that keeps sliding while traffic
continues.

**Acceptance Criteria**:
- [ ] Given a first hit at t0 with `decay`, when more hits land before t0+decay, then the window stays anchored at t0+decay.
- [ ] Given the window has elapsed, when the next hit lands, then a fresh window starts and the attempt is allowed.
- [ ] Given a key at its cap within the window, when another attempt lands, then it's denied without extending the window.
- [ ] Given `remaining(key)` after the window elapses, then it returns `max_attempts` again.

**Security Requirements**:
- [ ] Limiter fails toward denial within the window (cap enforced); window expiry is the only path back to allowed.

**Documentation Requirements**:
- [ ] `features/cache.md` documents the fixed window and the concurrency caveat (use `Throttle`/Redis for race-free distributed limiting).

**Requirement Refs**: SPEC-1, SPEC-2
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Type-safe, regression-covered
**As a** maintainer, **I want** the window logic typed and covered by clock-driven
tests, **so that** the fixed-window contract can't silently regress.

**Acceptance Criteria**:
- [ ] Given the type gate, when I run mypy --strict and pyright, then zero errors and no new bare `# type: ignore`.
- [ ] Given a controllable clock, when the suite runs, then sliding-window behaviour is rejected without real-time sleeps.

**Requirement Refs**: SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Related: WI-arvel-030 confirmed the `Throttle` login path keys on the real peer.

## Notes
- Cross-process atomicity of the cache-backed limiter is a documented limitation
  (no atomic `increment`/`add` on the `CacheStore` protocol; same stance as
  `Cache.lock()`/`remember()`). The `Throttle` middleware's Redis `INCR` store is
  the race-free option for distributed throttling.
