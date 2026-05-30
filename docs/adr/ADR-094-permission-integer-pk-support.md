# ADR-094 — arvel-permission integer PK support strategy

**Date**: 2026-05-23
**Status**: Accepted

## Context

`ModelHasRole.model_id` is `VARCHAR(36)` (Spatie compatibility). Models with integer PKs must
currently write `cast(model_id, Integer)` + `# type: ignore[attr-defined]` in every relationship
definition. Three options were considered:

1. **Autodetect** — inspect the host model's mapped PK column type at class creation time
2. **Config flag on ModelHasRole** — add `model_id_type: Literal["int", "str"]` to the pivot
3. **Helper factory function** — provide `make_roles_relationship(model_cls)` that returns
   the correctly-cast relationship based on the model's PK type

## Decision

Option 3: provide `make_roles_relationship(model_cls)` and `make_permissions_relationship(model_cls)`
helper functions in `arvel_permission.traits`.

## Rationale

- Autodetect (Option 1) requires reading SQLAlchemy mapper metadata at import time, which can
  fail if the mapper hasn't been configured yet (common with deferred setup)
- Config flag (Option 2) still requires the user to pass the config everywhere
- Factory functions encapsulate the cast logic inside the library. The consumer calls
  `roles = make_roles_relationship(User)` once, and the library inspects the PK type at
  relationship construction time — which happens after the mapper is fully configured

The factory pattern keeps the `# type: ignore` inside the library, not in consuming models.

## Consequences

- Demo `User` model removes the two `cast(..., Integer)` + `# type: ignore[attr-defined]` lines
- Existing models using VARCHAR PKs continue to work with no change (factory detects type)
- `arvel_permission.traits` exports `make_roles_relationship` and `make_permissions_relationship`
- `arvel_permission` README updated to show the factory usage
