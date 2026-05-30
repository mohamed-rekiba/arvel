# ADR-094 — arvel-permission pivot persistence and integer PK support

**Date**: 2026-05-23
**Status**: Superseded by [ADR-122](ADR-122-async-morph-to-many-permission.md)

> **Superseded.** The association-object + `association_proxy` design below was
> replaced by the async-first `MorphToMany` relation. The two problems this ADR
> solved (constant-join `model_type`-NULL persistence and integer-PK casts) are
> both absorbed by `MorphToMany`'s accessor, which writes the discriminator and
> string-casts the owner PK on every INSERT. The factories
> (`make_role_assignments`, `roles_proxy`, etc.) and the `ModelHasRole` /
> `ModelHasPermission` model classes no longer exist. See ADR-122.

## Context

The `model_has_roles` / `model_has_permissions` pivots are polymorphic: each row carries a
`model_type` discriminator plus a `model_id` (`VARCHAR(36)` for Spatie compatibility). Two problems
fell out of the original design.

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
