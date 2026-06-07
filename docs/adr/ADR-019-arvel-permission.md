# ADR-019 — `arvel-permission`

**Status**: Accepted
**Date**: original decisions 2026-05-20 – 2026-05-30; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Workspace-member RBAC + polymorphic permissions, standalone event system, exception hierarchy, async MorphToMany pivot mapping.

## Why this is one ADR

Four decisions that together define the package: how it stores authorization, how it emits events without depending on the framework's event bus, how it shapes its exceptions, and how it maps async polymorphic pivots cleanly. Splitting them across files obscured how each one falls out of the previous.

---

## § 1 — `arvel-permission` package

**Originally**: ADR-128 · Date: 2026-05-20

### Context

Roles and permissions are the most common authorization need above and beyond
Arvel's built-in `Gate`. Three design questions came up at the start:

1. **Where does it live?** Inside a single `arvel` PyPI package, or a standalone workspace member?
2. **What's it called?** "Identity" vs "permission" — they mean different things.
3. **API shape?** Bare wrappers around Arvel's `Gate`, or a richer model that owns its own storage?

### Constitutional check

Constitution Article III says: *"Splitting into per-feature PyPI packages is deferred to post-1.0 and requires real user demand."*

The user's explicit request is the "real user demand" condition. Consequence: a per-feature package is allowed *for this feature*, but the new package does not graduate to standalone PyPI distribution until 1.0.

### Decision

1. **Workspace member**: Ship `arvel-permission` as `packages/arvel-permission/` with its own `pyproject.toml`. Inside the monorepo it's a real package; outside, users get it via the `arvel[permission]` extra (which simply has `arvel-permission` as a dep).
2. **Name**: The package is `arvel-permission`. "Identity" was rejected — in industry parlance "identity" means authentication (who the user is), which `arvel.auth` already covers. This package is pure authorization (what the user can do), so "permission" is the precise term.
3. **Rich API, not a `Gate` wrapper**: Expose snake_case methods (`assign_role`, `has_role`, `give_permission_to`, etc.) directly on host models via `HasRoles` and `HasPermissions` mixins. The methods do the DB lookup directly; the `PermissionServiceProvider` registers each permission with `Gate` for cross-cutting use.
4. **Storage**: Five tables — `roles`, `permissions`, `model_has_roles`, `model_has_permissions`, `role_has_permissions` — UUID primary keys (Arvel-wide convention), `(name, guard_name)` composite unique on roles and permissions.
5. **Guards**: Default to `web`. `PermissionConfig.default_guard_name` is the override. Mixing guards raises `GuardMismatchError`.
6. **Caching**: In-process per-`PermissionRegistrar`, invalidated by `refresh_cache()`. Redis/distributed caching is a follow-up WI.
7. **Polymorphic association**: `model_type + model_id` on the pivots, so any model can own roles or permissions, not just `User`.

### Consequences

✅ The `HasRoles` / `HasPermissions` mixins read like normal model methods — no `Gate.allows("permission", user)` ceremony.
✅ No semantic overlap with `arvel.auth` — authentication stays in core; authorization is the package.
✅ Workspace gating means changes are batched with framework releases — no separate cadence pre-1.0.
✅ Plays well with `Gate` and the existing `Can` middleware.

⚠️ Constitution Article III now has a documented exception. ADR-020 follows the same path. We monitor for proliferation; if a third "extra package" lands without a clear case, we revisit Article III at 1.0.
⚠️ The in-process cache is correct for single-process deployments. Multi-process / multi-server setups must call `refresh_cache()` after writes or accept eventual consistency. Documented in the README.

### Alternatives considered

- **(A) `arvel.permission` submodule of arvel core** — fewer files, simpler ship. Rejected: bloats `arvel`'s base install for users who don't need permissions.
- **(B) `arvel-identity` as the package name** — initially proposed. Rejected on review: "identity" conflicts with the meaning of `arvel.auth` (authentication). The corrected name is `arvel-permission`.
- **(C) Pure wrapper around `Gate`** — minimal code. Rejected: a thin wrapper forces every consumer to re-invent role storage, guard scoping, and the role/permission graph themselves.

---

### Merged: Role hierarchy — numeric level rejected, use role names (was ADR-019 § 1)

**Status**: Rejected (superseded by decision to keep RBAC name-based)
**Date**: 2026-05-24

### Context

GAP-002 proposed adding a `level` integer to `Role` and `has_level(max_level)` to `HasRoles`
to support RBAC hierarchy checks without enumerating every possible role name.

### Decision

**Do not add `Role.level` or `has_level()`.** The role name is the authority.

Use `has_role("admin")` or `has_any_role("admin", "superadmin")` for hierarchy checks.
A numeric level adds a second source of truth that callers must keep in sync with business
meaning, introduces ordering ambiguity (higher or lower = more privileged?), and solves a
problem that `HasRoles` already handles with explicit role names.

### Consequences

- Positive: No extra column to seed or maintain.
- Positive: Access control reads as intent — `has_role("admin")` is self-documenting.
- Negative: None — `has_role` / `has_any_role` / `has_all_roles` cover all hierarchy cases.

---

### Merged: Remove demo HasRolesMixin in favour of framework HasRoles/HasPermissions (was ADR-019 § 1)

**Status**: Accepted
**Date**: 2026-05-24

### Context

After WI-036 removed the `Role.level` concept, `HasRolesMixin` in the demo became dead code. `User` inherited from both `HasRolesMixin` (sync, level-based) and `HasRoles`/`HasPermissions` (async, name-based). `is_admin` called `self.has_level(80)` which used `_max_level` — a field populated by old route helpers that were deleted in WI-037.

### Decision

Delete `app/mixins/has_roles.py`. Replace `User.is_admin` body with `self.has_any_role("admin", "super_admin")` using the `HasRoles` trait already in the MRO.

### Consequences

- `User.is_admin` is now correct: it checks actual loaded role names rather than a populated int field.
- No other model used `HasRolesMixin`.
- `has_level()` is gone; any future callers get an `AttributeError` rather than silent wrong results.

---

## § 2 — arvel-permission: Standalone event system

**Originally**: ADR-129 · Date: 2026-05-24

### Context

`arvel-permission` mutates state (role assigned, permission revoked, roles
synced, etc.) and downstream callers — audit logs, cache invalidators, ops
dashboards — want to react. The package owns its event surface. Three options:

1. Integrate with Arvel's event dispatcher (requires the `arvel` container at runtime).
2. Standalone pub/sub in `events.py` (no dependency on the container).
3. Callback hook attribute on the mixin.

### Decision

Option 2 — standalone `events.py` with a module-level listener registry. Opt-in via
`PermissionConfig.events_enabled`. The container is accessed lazily only when `events_enabled=True`
and an event fires.

### Consequences

- Positive: Package remains independently testable without the full Arvel container.
- Positive: Zero overhead when `events_enabled=False` (default).
- Negative: Not integrated with Arvel's event queue/replay — listeners are in-process only.
  Acceptable for the current use case (audit logging, cache invalidation).

---

## § 3 — arvel-permission: UnauthorizedException as a typed exception

**Originally**: ADR-130 · Date: 2026-05-24

### Context

Middleware currently returns an HTTP response directly from `__call__`. This means:
1. Callers can't differentiate "user unauthenticated" from "user lacks role" programmatically.
2. The HTTP response format is hardcoded and can't be customised without modifying middleware.
3. No exception is raised, so structured error logging hooks can't intercept auth failures.

### Decision

Add `UnauthorizedException(ArvelPermissionError)` with a `status_code: int` attribute.
Middleware raises it instead of returning a response directly. A fallback catch in middleware
converts it to HTTP if nothing handles it first.

### Consequences

- Positive: Callers can catch and handle auth failures (custom responses, audit logs).
- Positive: Framework exception handlers get a shot at formatting the error.
- Negative: Small breaking change if any code catches the raw HTTP response — acceptable because
  the fallback preserves identical HTTP output.

---

## § 4 — Async MorphToMany for arvel-permission pivots

**Originally**: ADR-131 · Date: 2026-05-30

Supersedes [ADR-019 § 4](ADR-019-arvel-permission.md). Keeps the composite-PK
schema from [ADR-019 § 4](ADR-019-arvel-permission.md); only the ORM mapping changes.

### Context

ADR-019 § 4 modelled the `model_has_roles` / `model_has_permissions` pivots as association
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

### Decision

Add a first-class `MorphToMany` async descriptor to Arvent and map the permission pivots through it.

- **`arvel.database.orm.morph_to_many`** — `MorphToMany(Related, *, table, name, related_key)`
  descriptor (declared `ClassVar` on host models) plus a `MorphToManyAccessor` bound per instance.
  The pivot carries `{name}_type` (ADR-008 § 4 short class name) and `{name}_id` (the **string-cast**
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

### Rationale

- One framework relation type replaces a stack of raw-SQLAlchemy workarounds. Consuming models
  declare two `ClassVar` descriptors and nothing else — no link collection, no proxy, no factories.
- Each grant/revoke persists through the accessor's own session round-trip, so there's no
  in-memory list to forget to flush and no eager-load requirement.
- The accessor dedups before INSERT, so `assign_role` is idempotent without depending on the
  composite-PK `IntegrityError` as control flow.

### Consequences

- **Removed**: `make_role_assignments`, `make_permission_assignments`, `roles_proxy`,
  `permissions_proxy`, `_StringId`, and the three association-object classes. Host models that
  followed ADR-019 § 4 must switch to the `MorphToMany` declaration in `docs/site/docs/permission.md`.
- **Async-only API**: all mixin methods now require `await`. The demo, guards, middleware, and
  services were updated accordingly; `User.is_admin` is now `async def`.
- **No `with_("roles","permissions")`**: load via `await user.roles.all()` /
  `await user.get_all_permissions()`. `where_has` / `with_count` still work.
- The composite-PK pivot schema (ADR-019 § 4) is unchanged — only the mapping moved from association
  objects to Core `Table`s + `MorphToMany`.
- Coverage: `packages/arvel/tests/database/test_morph_to_many.py` plus the rewritten async
  `arvel-permission` suites (`test_045`, `test_051`, `test_052`, `test_integer_pk`,
  `test_permissions`).

---

### Merged: arvel-permission pivot persistence and integer PK support (was ADR-019 § 4)

**Date**: 2026-05-23
**Status**: Superseded by [ADR-019 § 4](ADR-019-arvel-permission.md)

> **Superseded.** The association-object + `association_proxy` design below was
> replaced by the async-first `MorphToMany` relation. The two problems this ADR
> solved (constant-join `model_type`-NULL persistence and integer-PK casts) are
> both absorbed by `MorphToMany`'s accessor, which writes the discriminator and
> string-casts the owner PK on every INSERT. The factories
> (`make_role_assignments`, `roles_proxy`, etc.) and the `ModelHasRole` /
> `ModelHasPermission` model classes no longer exist. See ADR-019 § 4.

### Context

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

### Decision

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

### Rationale

- An association object is a normal mapped row, so every column (including `model_type`) is
  persisted on insert. The `secondary` table approach cannot guarantee that for constant-join
  columns.
- The `association_proxy` keeps the ergonomic `user.roles.append(role)` / `user.has_role(...)` API
  unchanged; mixin methods still operate on a plain `list`.
- The query builder's eager loader expands proxy paths (`roles` → `role_assignments.role`,
  `roles.permissions` → `role_assignments.role.permissions`), so `with_("roles")` keeps working.
- The cast logic stays inside the library — consuming models need no `cast()` or `# type: ignore`.

### Consequences

- Host models declare both the link collection and the proxy (see `docs/site/docs/permission.md`).
- `arvel_permission.traits` exports `make_role_assignments`, `make_permission_assignments`,
  `roles_proxy`, and `permissions_proxy`. The old `make_roles_relationship` /
  `make_permissions_relationship` factories are gone.
- `ModelHasRole` / `ModelHasPermission` are association objects with a `role` / `permission`
  relationship and an FK-backed `role_id` / `permission_id` (set via the relationship, `init=False`).
- Regression coverage lives in `packages/arvel-permission/tests/test_052_pivot_discriminator.py`
  (a grant survives a fresh session; removing a role deletes its pivot row).

---

### Merged: Permission Pivot Tables: Composite Primary Key (was ADR-019 § 4)

**Status**: Accepted
**Date**: 2026-05-24

### Context

`model_has_roles` and `model_has_permissions` in were given surrogate `id` integer
PKs and `Timestamps` mixin columns. A post-release review (Finding #1, CRITICAL) found:

1. No uniqueness constraint on `(role_id, model_id, model_type)` — duplicate assignments are
   possible through any code path that bypasses the in-memory deduplication in `assign_role`.
2. `Timestamps` and `id` diverge from the canonical pure-pivot schema used everywhere else
   in the framework — keeping them invites schema drift across packages.
3. SQLAlchemy treats tables with surrogate PKs differently in `relationship(..., secondary=...)`
   write-through operations — the composite-key form is the canonical SQLAlchemy pattern for
   pure join tables.

### Decision

Replace surrogate `id` + `Timestamps` on both `ModelHasRole` and `ModelHasPermission` with
a composite primary key `(role_id, model_id, model_type)` and `(permission_id, model_id, model_type)`
respectively. No `created_at` / `updated_at` columns on either table.

`RoleHasPermission` already uses a composite PK — no change there.

### Consequences

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

### Alternatives Considered

**(A) Keep surrogate PK, add `UNIQUE(role_id, model_id, model_type)` constraint** — would fix
the data integrity issue without breaking migration. Rejected: still diverges from the canonical
pure-pivot shape, and adds an index that's redundant with the primary key in the composite-PK
design.

**(B) Keep surrogate PK, enforce uniqueness in application code only** — Rejected: application-
level deduplication is insufficient for concurrent writes. Security mitigation must be at the
DB constraint level.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-128 | 2026-05-20 | `arvel-permission` package | § 1 |
| ADR-129 | 2026-05-24 | arvel-permission: Standalone event system | § 2 |
| ADR-130 | 2026-05-24 | arvel-permission: UnauthorizedException as a typed exception | § 3 |
| ADR-131 | 2026-05-30 | Async MorphToMany for arvel-permission pivots | § 4 |
