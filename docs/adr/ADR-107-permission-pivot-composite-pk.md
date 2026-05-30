# ADR-107 — Permission Pivot Tables: Composite Primary Key

**Status**: Accepted
**Date**: 2026-05-24

## Context

`model_has_roles` and `model_has_permissions` in were given surrogate `id` integer
PKs and `Timestamps` mixin columns. A post-release review (Finding #1, CRITICAL) found:

1. No uniqueness constraint on `(role_id, model_id, model_type)` — duplicate assignments are
   possible through any code path that bypasses the in-memory deduplication in `assign_role`.
2. `Timestamps` and `id` diverge from Spatie's default migration schema, breaking cross-tool
   compatibility expectations.
3. SQLAlchemy treats tables with surrogate PKs differently in `relationship(..., secondary=...)`
   write-through operations — the composite-key form is the canonical SQLAlchemy pattern for
   pure join tables.

## Decision

Replace surrogate `id` + `Timestamps` on both `ModelHasRole` and `ModelHasPermission` with
a composite primary key `(role_id, model_id, model_type)` and `(permission_id, model_id, model_type)`
respectively. No `created_at` / `updated_at` columns on either table.

`RoleHasPermission` already uses a composite PK — no change there.

## Consequences

**Positive**:
- DB-level uniqueness guarantee: duplicate assignment raises `IntegrityError` regardless of
  which code path does the insert.
- Schema matches Spatie's default migration — consuming apps porting from PHP can apply the
  same migration tooling expectations.
- SQLAlchemy `relationship(..., secondary=..., viewonly=False)` works correctly with composite
  PKs for insert/delete on the join table.

**Negative / Mitigations**:
- **Breaking migration**: Any app that already applied the WI-025 migration must drop and
  recreate the pivot tables. Acceptable at pre-1.0. Migration `down()` drops both tables.
- `ModelHasRole` and `ModelHasPermission` lose their `id` attribute — any code that accessed
  `pivot.id` will break. No such code exists in the current codebase.

## Alternatives Considered

**(A) Keep surrogate PK, add `UNIQUE(role_id, model_id, model_type)` constraint** — would fix
the data integrity issue without breaking migration. Rejected: still diverges from Spatie schema;
adds an index that's redundant with the primary key in the composite-PK design.

**(B) Keep surrogate PK, enforce uniqueness in application code only** — Rejected: application-
level deduplication is insufficient for concurrent writes. Security mitigation must be at the
DB constraint level.
