# ADR-049: Soft-Delete Filter as GlobalScope

**Status**: Accepted
**Date**: 2026-05-18

## Decision

`SoftDeletes.__init_subclass__` registers a `GlobalScope` named `"soft_delete"` on the model class. This scope appends `WHERE deleted_at IS NULL` to every SELECT query on the model.

## Context

The current implementation only gates instance-level `delete()`/`restore()`. It does NOT filter SELECTs, so `User.all()` returns soft-deleted rows — broken behavior.

## Options

**A. Override `query()` in `SoftDeletes`** — manually add the WHERE clause in a classmethod override. Brittle: any new QB entry point would need the same override.

**B. SQLAlchemy mapper `with_loader_criteria`** — register a criteria function at the mapper level. Works but couples the soft-delete to SQLAlchemy internals more deeply than necessary.

**C. GlobalScope mechanism** ← chosen. The existing `GlobalScope` machinery in arvel is the right abstraction. `with_trashed()` becomes `without_global_scope("soft_delete")` — the same pattern Laravel uses.

## Consequences

- All QB SELECT paths automatically exclude soft-deleted rows for `SoftDeletes` models
- `with_trashed()` and `only_trashed()` work uniformly across all QB entry points
- The scope name `"soft_delete"` is a string constant — import from `arvel.database.scope`
