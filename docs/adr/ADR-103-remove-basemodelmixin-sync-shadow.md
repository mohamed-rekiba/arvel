# ADR-103: Remove Sync Shadow Methods from BaseModelMixin

**Date**: 2026-05-24
**Status**: Accepted

## Context

`BaseModelMixin` in `arvel-ecommerce-demo` defines sync `delete()`, `restore()`,
`scope_active()`, `to_dict()`, and `__post_init__`. Because `BaseModelMixin` appears first
in every model's MRO, it shadows the async equivalents from `ActiveRecord` / `SoftDeletes`.

Consequence: routes can never `await product.delete()` — the sync method executes and
returns `None`, and `await None` raises `TypeError`. All route handlers bypass the framework
by using `DB.statement("UPDATE ... SET deleted_at = ...")` instead.

## Decision

Remove `delete()`, `restore()`, `scope_active()`, `to_dict()`, and `__post_init__` from
`BaseModelMixin`. After removal, MRO resolution reaches `ActiveRecord.delete()` (async),
which already handles soft-delete via `__arvel_soft_delete_column__`.

The unit test `test_model_mixins.py::TestBaseModelMixin` that calls `p.delete()` sync is
updated: the tests set `p.deleted_at` directly or are removed, as the async counterparts
are covered by integration tests.

## Consequences

- Routes can now call `await product.delete()` / `await product.restore()` correctly
- No raw SQL `UPDATE ... SET deleted_at = :now` needed in services or routes
- Unit tests that tested sync behavior are updated to set attribute directly
- `BaseModelMixin` now contains only: class docstring and the `uuid7` re-export line
