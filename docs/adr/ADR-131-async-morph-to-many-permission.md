# ADR-131 — Async MorphToMany for arvel-permission pivots

**Date**: 2026-05-30
**Status**: Accepted

Supersedes [ADR-131](ADR-131-async-morph-to-many-permission.md). Keeps the composite-PK
schema from [ADR-131](ADR-131-async-morph-to-many-permission.md); only the ORM mapping changes.

## Context

ADR-131 modelled the `model_has_roles` / `model_has_permissions` pivots as association
objects (`ModelHasRole` / `ModelHasPermission`) fronted by an `association_proxy`, to fix two
problems: the `model_type`-NULL persistence bug from a constant-join `secondary` mapping, and
the `cast(model_id, Integer)` + `# type: ignore` boilerplate integer-PK hosts had to write.

That design predated a polymorphic many-to-many relation in Arvent. The framework now has
`MorphOne` / `MorphMany` / `BelongsToMany` async descriptors but no polymorphic many-to-many, so
`arvel-permission` was the only consumer still reaching for raw SQLAlchemy (`relationship` +
`association_proxy` + a `_StringId` `TypeDecorator`). Two further frictions surfaced:

1. **Sync/async split.** The mixin methods (`assign_role`, `has_permission_to`, …) operated on an
   in-memory `list` and relied on a later `await user.save()` to flush. That hid persistence
   behind a separate step and forced eager loading via `with_("roles","permissions")`.
2. **`with_()` can't load custom descriptors.** `QueryBuilder.with_()` only resolves SQLAlchemy
   `mapper.relationships`, so any framework-native async relation needs on-demand accessors anyway.

Per the project directive: async-first, no backward compatibility.

## Decision

Add a first-class `MorphToMany` async descriptor to Arvent and map the permission pivots through it.

- **`arvel.database.orm.morph_to_many`** — `MorphToMany(Related, *, table, name, related_key)`
  descriptor (declared `ClassVar` on host models) plus a `MorphToManyAccessor` bound per instance.
  The pivot carries `{name}_type` (ADR-066 short class name) and `{name}_id` (the **string-cast**
  owner PK). Writing and comparing `model_id` as a string lets one `VARCHAR(36)` column accept
  integer, UUID, and string PKs with no dialect-specific cast — this absorbs `_StringId`.
- **Accessor methods** are all async: `attach`, `detach`, `sync`, `sync_without_detaching`,
  `toggle`, `all`, `pivot`, `where_pivot`, and `__aiter__`. Every INSERT/SELECT/DELETE sets both
  discriminator columns, so the `model_type`-NULL bug class is structurally impossible.
- **`link_spec()`** returns a `MorphToManyLink` so `_resolve_relation` in `query.py` supports
  `where_has` / `with_count` for `MorphToMany`, alongside the existing `BelongsToMany` branch.
- **arvel-permission** drops `_StringId`, `ModelHasRole`, `ModelHasPermission`, and
  `RoleHasPermission` model classes. The three pivots become plain Core `Table`s on
  `Model.metadata`. `Role.permissions` / `Permission.roles` are `BelongsToMany` over
  `role_has_permissions`. `HasRoles` / `HasPermissions` are rewritten async — `roles` /
  `permissions` are `MorphToMany` accessors and every method (`assign_role`, `has_role`,
  `has_level`, `give_permission_to`, `has_permission_to`, `get_all_permissions`, …) is `async`.

## Rationale

- One framework relation type replaces a stack of raw-SQLAlchemy workarounds. Consuming models
  declare two `ClassVar` descriptors and nothing else — no link collection, no proxy, no factories.
- Each grant/revoke persists through the accessor's own session round-trip, so there's no
  in-memory list to forget to flush and no eager-load requirement.
- The accessor dedups before INSERT, so `assign_role` is idempotent without depending on the
  composite-PK `IntegrityError` as control flow.

## Consequences

- **Removed**: `make_role_assignments`, `make_permission_assignments`, `roles_proxy`,
  `permissions_proxy`, `_StringId`, and the three association-object classes. Host models that
  followed ADR-131 must switch to the `MorphToMany` declaration in `docs/site/docs/permission.md`.
- **Async-only API**: all mixin methods now require `await`. The demo, guards, middleware, and
  services were updated accordingly; `User.is_admin` is now `async def`.
- **No `with_("roles","permissions")`**: load via `await user.roles.all()` /
  `await user.get_all_permissions()`. `where_has` / `with_count` still work.
- The composite-PK pivot schema (ADR-131) is unchanged — only the mapping moved from association
  objects to Core `Table`s + `MorphToMany`.
- Coverage: `packages/arvel/tests/database/test_morph_to_many.py` plus the rewritten async
  `arvel-permission` suites (`test_045`, `test_051`, `test_052`, `test_integer_pk`,
  `test_permissions`).

---

## Merged: arvel-permission pivot persistence and integer PK support (was ADR-131)

**Date**: 2026-05-23
**Status**: Superseded by [ADR-131](ADR-131-async-morph-to-many-permission.md)

> **Superseded.** The association-object + `association_proxy` design below was
> replaced by the async-first `MorphToMany` relation. The two problems this ADR
> solved (constant-join `model_type`-NULL persistence and integer-PK casts) are
> both absorbed by `MorphToMany`'s accessor, which writes the discriminator and
> string-casts the owner PK on every INSERT. The factories
> (`make_role_assignments`, `roles_proxy`, etc.) and the `ModelHasRole` /
> `ModelHasPermission` model classes no longer exist. See ADR-131.

## Context

The `model_has_roles` / `model_has_permissions` pivots are polymorphic: each row carries a
`model_type` discriminator plus a `model_id` (`VARCHAR(36)` to fit any of Arvel's standard
PK encodings — int as digits, UUID as canonical string). Two problems fell out of the
original design.

1. **Persistence bug.** The host model wired `roles` / `permissions` as a plain `secondary`
   many-to-many whose `primaryjoin` pinned `model_type` to a constant. SQLAlchemy does **not**
   persist a constant-join column on insert, so `model_type` went in as `NULL`. With `model_type`
   part of the composite primary key (`NOT NULL`), API-assigned grants either violated the
   constraint or silently vanished on the next request.
2. **Integer PK ergonomics.** Models with integer PKs had to write `cast(model_id, Integer)` +
   `# type: ignore[attr-defined]` in every relationship definition.

## Decision

Model the pivots as **first-class association objects** and expose the far side through an
**`association_proxy`**.

`arvel_permission.traits` provides four factories:

- `make_role_assignments(getter, *, model_type)` / `make_permission_assignments(...)` — build the
  link collection (`role_assignments` / `permission_assignments`) of `ModelHasRole` /
  `ModelHasPermission` rows.
- `roles_proxy(*, model_type)` / `permissions_proxy(...)` — build the `association_proxy` that
  presents `roles` / `permissions` as a `list[Role]` / `list[Permission]`.

The proxy's `creator` constructs each pivot row explicitly, stamping `model_type` — so the
discriminator is always written. The link factories also cast the integer PK to `VARCHAR(36)`
internally.

## Rationale

- An association object is a normal mapped row, so every column (including `model_type`) is
  persisted on insert. The `secondary` table approach cannot guarantee that for constant-join
  columns.
- The `association_proxy` keeps the ergonomic `user.roles.append(role)` / `user.has_role(...)` API
  unchanged; mixin methods still operate on a plain `list`.
- The query builder's eager loader expands proxy paths (`roles` → `role_assignments.role`,
  `roles.permissions` → `role_assignments.role.permissions`), so `with_("roles")` keeps working.
- The cast logic stays inside the library — consuming models need no `cast()` or `# type: ignore`.

## Consequences

- Host models declare both the link collection and the proxy (see `docs/site/docs/permission.md`).
- `arvel_permission.traits` exports `make_role_assignments`, `make_permission_assignments`,
  `roles_proxy`, and `permissions_proxy`. The old `make_roles_relationship` /
  `make_permissions_relationship` factories are gone.
- `ModelHasRole` / `ModelHasPermission` are association objects with a `role` / `permission`
  relationship and an FK-backed `role_id` / `permission_id` (set via the relationship, `init=False`).
- Regression coverage lives in `packages/arvel-permission/tests/test_052_pivot_discriminator.py`
  (a grant survives a fresh session; removing a role deletes its pivot row).

---

## Merged: Permission Pivot Tables: Composite Primary Key (was ADR-131)

**Status**: Accepted
**Date**: 2026-05-24

## Context

`model_has_roles` and `model_has_permissions` in were given surrogate `id` integer
PKs and `Timestamps` mixin columns. A post-release review (Finding #1, CRITICAL) found:

1. No uniqueness constraint on `(role_id, model_id, model_type)` — duplicate assignments are
   possible through any code path that bypasses the in-memory deduplication in `assign_role`.
2. `Timestamps` and `id` diverge from the canonical pure-pivot schema used everywhere else
   in the framework — keeping them invites schema drift across packages.
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
- Schema matches the standard pure-pivot shape used elsewhere in Arvel — uniform expectations
  across the framework.
- SQLAlchemy `relationship(..., secondary=..., viewonly=False)` works correctly with composite
  PKs for insert/delete on the join table.

**Negative / Mitigations**:
- **Breaking migration**: Any app that already applied the WI-025 migration must drop and
  recreate the pivot tables. Acceptable at pre-1.0. Migration `down()` drops both tables.
- `ModelHasRole` and `ModelHasPermission` lose their `id` attribute — any code that accessed
  `pivot.id` will break. No such code exists in the current codebase.

## Alternatives Considered

**(A) Keep surrogate PK, add `UNIQUE(role_id, model_id, model_type)` constraint** — would fix
the data integrity issue without breaking migration. Rejected: still diverges from the canonical
pure-pivot shape, and adds an index that's redundant with the primary key in the composite-PK
design.

**(B) Keep surrogate PK, enforce uniqueness in application code only** — Rejected: application-
level deduplication is insufficient for concurrent writes. Security mitigation must be at the
DB constraint level.
