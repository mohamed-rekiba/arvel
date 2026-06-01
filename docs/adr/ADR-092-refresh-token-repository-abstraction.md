# ADR-092 — `RefreshTokenRepository` as a swappable abstraction

**Date**: 2026-05-21
**Status**: Accepted
**Context**:
**Supersedes**: nothing
**Superseded by**: nothing

---

## Context

shipped `RefreshTokenRepository` as an ABC and an in-memory
implementation. WI-027's kit then bypassed the ABC entirely and wrote raw
SQL inside `AuthService`, hitting `personal_access_tokens` directly. That
approach surfaced FB-027-007: standalone `DB.statement()` calls outside an
explicit transaction never commit, causing silent rollbacks of refresh-token
inserts.

We need a production-grade refresh-token store, and we want it swappable
(some users will want Redis for sub-millisecond lookup; some will want
encrypted columns; some will want to mix-in WORM audit storage).

## Decision

The framework ships **`DatabaseRefreshTokenRepository`** as the default
implementation of `arvel.auth.RefreshTokenRepository`. It uses the framework's
ORM (`User`, `personal_access_tokens` table mapped via SQLAlchemy) and
**always wraps writes in `DB.transaction()`** — no standalone statements.

The abstraction is bound in `AuthServiceProvider.register()`:

```python
self.container.bind(
    RefreshTokenRepository,
    DatabaseRefreshTokenRepository,
)
```

Users override by re-binding in their own `AuthServiceProvider`. The interface
is:

```python
class RefreshTokenRepository(ABC):
    async def store(self, *, user_id: int, token_hash: str, ttl: timedelta) -> RefreshTokenRecord: ...
    async def find(self, *, token_hash: str) -> RefreshTokenRecord | None: ...
    async def rotate(self, *, old_hash: str, new_hash: str, user_id: int, ttl: timedelta) -> RefreshTokenRecord: ...
    async def delete(self, *, token_hash: str) -> None: ...
    async def delete_all_for_user(self, *, user_id: int) -> int: ...
    async def delete_family(self, *, user_id: int) -> int: ...
```

## Drivers

1. **Closes FB-027-007.** Every write goes through `DB.transaction()`,
   guaranteeing commit.
2. **Token-family revocation needs a uniform delete-all method.** Inline SQL
   in the broker would duplicate this logic across `reset_password`,
   `logout_others`, and the reuse-detection branch.
3. **Test isolation.** Unit tests for the broker can swap in
   `InMemoryRefreshTokenRepository` and stay fast.
4. **Customisability.** Users wanting Redis-backed refresh tokens
   (sub-millisecond) can plug in their own implementation — no fork.

## Alternatives considered

### A. Continue with raw SQL inside `AuthBroker`

**Pros**: nothing.

**Cons**:
- Reproduces FB-027-007 forever.
- Couples broker to schema.
- Hard to test (every broker test needs a real DB).

**Rejected**.

### B. Use SQLAlchemy ORM model (`PersonalAccessToken`) directly in broker

**Pros**:
- One layer fewer than the repo abstraction.

**Cons**:
- Same coupling problem as A.
- Loses the swap-out point for Redis/in-memory.
- Tests still need a DB.

**Rejected**.

### C. Use Redis as the default

**Pros**:
- Sub-millisecond lookup.

**Cons**:
- Adds a hard dependency on Redis for every Arvel app.
- Refresh tokens benefit from durability + audit; Redis is in-memory.

**Rejected** — keep DB as default; Redis is a user choice via the abstraction.

## Consequences

### Positive

- One canonical place for refresh-token storage.
- Explicit transaction boundaries kill the silent-rollback bug class.
- Token-family revocation is a single method call.
- Tests stay fast (`InMemoryRefreshTokenRepository`).

### Negative

- One more layer between broker and DB. Acceptable; the broker is a
  high-frequency-of-change surface and the repo lets us iterate without
  schema changes.

### Neutral

- The `personal_access_tokens` table schema doesn't change; the repo
  reads/writes the same columns the kit's raw SQL does.

## Validation

- FR-028-13..17 in PRD-028 all pass.
- `unit/test_refresh_tokens.py` covers store/find/rotate/delete/delete_family.
- `integration/test_provider.py` confirms the binding swap works.
- Token-reuse detection test (FR-028-15) deletes every refresh token for the
  user when an unknown but valid hash is presented.
