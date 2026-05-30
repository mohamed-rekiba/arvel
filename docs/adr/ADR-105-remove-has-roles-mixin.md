# ADR-105: Remove demo HasRolesMixin in favour of framework HasRoles/HasPermissions

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
