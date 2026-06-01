# ADR-093: Auth Middleware and ORM Correctness Fixes

**Date**: 2026-05-24
**Status**: Accepted

---

## ADR-042-001: Save event detection via inspect().pending

**Context**: `Model.save()` must distinguish insert from update to fire the correct lifecycle event. SQLAlchemy tracks instance state in its identity map.

**Decision**: Snapshot `was_pending = sqla_inspect(self).pending` before `session.add(self)`. Fire `"created"` if `was_pending`, else `"updated"`.

**Alternatives considered**:
- Check `inspect(self).transient` — True before any `add()`, but snapshot still required before the add.
- Check DB primary key — unreliable for models with server-side default PKs before flush.
- `inspect(self).persistent` — the inverse; same approach.

**Consequence**: Correct lifecycle events reach listeners. No DB round-trip required.

---

## ADR-042-002: Authenticate resolves AuthManager not Guard

**Context**: The container may have multiple guards registered. `container.make(Guard)` resolves the last-bound `Guard` instance — undefined for multi-guard apps.

**Decision**: Call `container.make(AuthManager).guard(self._guard_name)`. This is type-safe since `AuthManager` is bound as a singleton by `AuthServiceProvider`.

**Consequence**: `guard_name="api"` now correctly selects the `api` guard. Apps with a single guard see no behavior change.
