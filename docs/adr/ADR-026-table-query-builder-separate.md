# ADR-026: TableQueryBuilder Is a Separate Class

**Status**: Accepted
**Date**: 2026-05-18

## Decision

`DB.table("users")` returns a `TableQueryBuilder` — a separate, non-generic class that is NOT a subclass of `QueryBuilder[T]`.

## Context

`QueryBuilder[T]` is bound to a specific SQLAlchemy `DeclarativeBase` model (`T`). It returns hydrated model instances. `DB.table()` should return raw dictionaries and accept any table name at runtime.

## Options

**A. `QueryBuilder[dict]`** — reuse the same class with `T = dict`. Technically possible but semantically misleading; the existing QB has model-specific logic (global scopes, relations) that doesn't apply to raw table access.

**B. Separate `TableQueryBuilder`** ← chosen. Clear separation of concerns; cleaner types; no leakage of model-specific QB behavior into raw table queries.

## Consequences

- `DB.table("users").get()` returns `list[dict[str, Any]]`
- `DB.table(...)` methods are a subset of `QueryBuilder` — no relations, no scopes, no soft-delete
- Duplication of some QB plumbing is acceptable; both classes share an internal `_execute_select` utility
