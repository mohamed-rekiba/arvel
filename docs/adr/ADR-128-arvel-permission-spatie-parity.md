# ADR-128 — `arvel-permission` package, Spatie Permission parity

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: —

## Context

Laravel apps overwhelmingly reach for `spatie/laravel-permission` to express roles and permissions. Migrating apps to Arvel without an equivalent forces every team to re-invent that wheel. Three design questions:

1. **Where does it live?** Inside a single `arvel` PyPI package, or a standalone workspace member?
2. **What's it called?** The package mirrors the Spatie upstream — authorization, not authentication.
3. **API shape?** Bare wrappers around Arvel's `Gate`, or a faithful Spatie shape?

## Constitutional check

Constitution Article III says: *"Splitting into per-feature PyPI packages is deferred to post-1.0 and requires real user demand."*

The user's explicit request via is the "real user demand" condition. Consequence: a per-feature package is allowed *for this feature*, but the new package does not graduate to standalone PyPI distribution until 1.0.

## Decision

1. **Workspace member**: Ship `arvel-permission` as `packages/arvel-permission/` with its own `pyproject.toml`. Inside the monorepo it's a real package; outside, users get it via the `arvel[permission]` extra (which simply has `arvel-permission` as a dep).
2. **Name mirrors the upstream**: The package is `arvel-permission`, matching `spatie/laravel-permission`. "Identity" was rejected — in industry parlance "identity" means authentication (who the user is), which `arvel.auth` already covers. This package is pure authorization (what the user can do), so "permission" is the precise term and the obvious search target for any developer porting from Laravel.
3. **Spatie API shape**: Mirror Spatie's method names (`assignRole` → `assign_role`, `hasRole` → `has_role`, `givePermissionTo` → `give_permission_to`, etc.) so a Laravel team can pattern-match. Don't wrap them in `arvel.gate` calls — the methods do the database lookup directly, then the `PermissionServiceProvider` registers each permission with `Gate` for cross-cutting use.
4. **Storage**: Five tables — `roles`, `permissions`, `model_has_roles`, `model_has_permissions`, `role_has_permissions` — same shape as Spatie's defaults, UUID primary keys (Arvel-wide convention), `(name, guard_name)` composite unique on roles and permissions.
5. **Guards**: Default to `web`. Spatie's `default_guard_name` config knob mirrored as `PermissionConfig.default_guard_name`. Mixing guards raises `GuardMismatchError`.
6. **Caching**: In-process per-`PermissionRegistrar`, invalidated by `refresh_cache()`. Redis/distributed caching is a follow-up WI.
7. **Polymorphic association**: `model_type + model_id` on the pivots, matching Spatie's polymorphic relationship.

## Consequences

✅ Laravel devs feel at home. The mapping table in the README pairs each Spatie method with its `arvel-permission` equivalent. The package name itself signals the search intent ("port of spatie/laravel-permission").
✅ No semantic overlap with `arvel.auth` — authentication stays in core; authorization is the package.
✅ Workspace gating means changes are batched with framework releases — no separate cadence pre-1.0.
✅ Plays well with `Gate` and the existing `Can` middleware.

⚠️ Constitution Article III now has a documented exception. ADR-132 follows the same path. We monitor for proliferation; if a third "extra package" lands without a clear case, we revisit Article III at 1.0.
⚠️ The in-process cache is correct for single-process deployments. Multi-process / multi-server setups must call `refresh_cache()` after writes or accept eventual consistency. Documented in the README.

## Alternatives considered

- **(A) `arvel.permission` submodule of arvel core** — fewer files, simpler ship. Rejected: doesn't honor the user's "two packages" request and bloats `arvel`'s base install for users who don't need permissions.
- **(B) `arvel-identity` as the package name** — initially proposed. Rejected on review: "identity" conflicts with the meaning of `arvel.auth` (authentication) and breaks symmetry with the upstream `spatie/laravel-permission`. The corrected name is `arvel-permission`.
- **(C) Pure wrapper around `Gate`** — minimal code. Rejected: misses Spatie's surface area (sync_roles, get_all_permissions, guard scoping) and forces users to learn Arvel-specific conventions before any of their Spatie muscle memory pays off.

---

## Merged: Role hierarchy — numeric level rejected, use role names (was ADR-128)

**Status**: Rejected (superseded by decision to keep RBAC name-based)
**Date**: 2026-05-24

## Context

GAP-002 proposed adding a `level` integer to `Role` and `has_level(max_level)` to `HasRoles`
to support RBAC hierarchy checks without enumerating every possible role name.

## Decision

**Do not add `Role.level` or `has_level()`.** The role name is the authority.

Use `has_role("admin")` or `has_any_role("admin", "superadmin")` for hierarchy checks.
A numeric level adds a second source of truth that callers must keep in sync with business
meaning, introduces ordering ambiguity (higher or lower = more privileged?), and solves a
problem that `HasRoles` already handles with explicit role names.

## Consequences

- Positive: No extra column to seed or maintain.
- Positive: Access control reads as intent — `has_role("admin")` is self-documenting.
- Negative: None — `has_role` / `has_any_role` / `has_all_roles` cover all hierarchy cases.

---

## Merged: Remove demo HasRolesMixin in favour of framework HasRoles/HasPermissions (was ADR-128)

**Status**: Accepted
**Date**: 2026-05-24

## Context

After WI-036 removed the `Role.level` concept, `HasRolesMixin` in the demo became dead code. `User` inherits from both `HasRolesMixin` (sync, level-based) and `HasRoles`/`HasPermissions` (async, Spatie-style). `is_admin` called `self.has_level(80)` which used `_max_level` — a field populated by old route helpers that were deleted in WI-037.

## Decision

Delete `app/mixins/has_roles.py`. Replace `User.is_admin` body with `self.has_any_role("admin", "super_admin")` using the `HasRoles` trait already in the MRO.

## Consequences

- `User.is_admin` is now correct: it checks actual loaded role names rather than a populated int field.
- No other model used `HasRolesMixin`.
- `has_level()` is gone; any future callers get an `AttributeError` rather than silent wrong results.
