# ADR-122 — Async MorphToMany for arvel-permission pivots

**Date**: 2026-05-30
**Status**: Accepted

Supersedes [ADR-094](ADR-094-permission-integer-pk-support.md). Keeps the composite-PK
schema from [ADR-107](ADR-107-permission-pivot-composite-pk.md); only the ORM mapping changes.

## Context

ADR-094 modelled the `model_has_roles` / `model_has_permissions` pivots as association
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
  The pivot carries `{name}_type` (ADR-022 short class name) and `{name}_id` (the **string-cast**
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
  followed ADR-094 must switch to the `MorphToMany` declaration in `docs/site/docs/permission.md`.
- **Async-only API**: all mixin methods now require `await`. The demo, guards, middleware, and
  services were updated accordingly; `User.is_admin` is now `async def`.
- **No `with_("roles","permissions")`**: load via `await user.roles.all()` /
  `await user.get_all_permissions()`. `where_has` / `with_count` still work.
- The composite-PK pivot schema (ADR-107) is unchanged — only the mapping moved from association
  objects to Core `Table`s + `MorphToMany`.
- Coverage: `packages/arvel/tests/database/test_morph_to_many.py` plus the rewritten async
  `arvel-permission` suites (`test_045`, `test_051`, `test_052`, `test_integer_pk`,
  `test_permissions`).
