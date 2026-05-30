# ADR-098: Role hierarchy — numeric level rejected, use role names

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
