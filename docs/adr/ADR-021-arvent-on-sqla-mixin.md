# ADR-021 — Arvent is a mixin on SQLAlchemy, not a fork

**Status**: Accepted
**Date**: 2026-05-17
**Supersedes**: —

## Context

Laravel's Eloquent is the gold standard for ActiveRecord ergonomics. Python
already has SQLAlchemy with first-class async support, fully typed
`Mapped[...]` annotations, and a mature query construction API. Three options
were considered:

| Option | Pros | Cons |
|---|---|---|
| A. Custom ORM (Masonite-style) | Total control over DX | Years of work to match SQLA's edge cases (identity map, unit of work, autoflush, polymorphic loading, etc.) |
| B. Light wrapper around SQLA Core (Uvicore-style) | Type-safe; less magic | Loses ActiveRecord ergonomics; falls back to data-mapper everywhere |
| C. **Mixin on SQLA 2.0 `DeclarativeBase`** | Eloquent-grade DX for free + SQLA's maturity; no schema fork | Some Laravel idioms (lazy-load-by-default) don't translate — we steer users toward eager-loading instead |

## Decision

Option C. `arvel.database.Model` extends SQLA 2.0 `DeclarativeBase` and applies
the `ActiveRecord` mixin pre-mounted. Every column type, relationship, and
query primitive is backed by an existing SQLA primitive. No re-implementation
of features SQLA already provides.

## Consequences

**Positive**:
- Users with SQLA experience are immediately productive.
- We inherit SQLA's bug fixes and performance improvements automatically.
- `mypy --strict` and `pyright --strict` "just work" because SQLA 2.0's
  `Mapped[...]` annotations are already first-class.
- Migrations through Alembic come for free.

**Negative**:
- Lazy-load by default doesn't translate well — async + lazy = footgun. We
  default to `lazy="raise"` on relations in the example apps and DX docs.
- Some Eloquent idioms (`whereHas`, `whereDoesntHave`) become SQLA `any()` /
  `has()` queries; we provide thin sugar but encourage SQLA expressions.

**Enforcement**:
- Code review checklist line item: "Does this re-implement a SQLA feature?"
  → reject and use the SQLA primitive.

---

## Merged: Remove Sync Shadow Methods from BaseModelMixin (was ADR-021)

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
