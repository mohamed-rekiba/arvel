# WI-arvel-025 — Model `where()` must accept Laravel's string column/operator/value form

- **Module**: 25 — ORM query builder (`QueryBuilder.where` / `or_where`)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`Model.where("email", "john@example.com")` and
`Model.where("email", "ilike", "john@example.com")` — the documented Laravel
forms — crashed with a SQLAlchemy `ArgumentError`:

```
ArgumentError: Textual SQL expression 'email' should be explicitly declared as text('email')
```

`QueryBuilder.where` (`packages/arvel/src/arvel/database/query.py`) only handled
three shapes: a SQLAlchemy expression (`Model.col == x`), a callable group, and
kwargs (`where(col=x)`). A bare string positional fell through to `_and(clause)`
→ `and_("email")`, and SQLAlchemy tried to coerce the column name as raw textual
SQL and rejected it. `or_where` shared the same gap via `_or_terms`.

The operator map (`_apply_operator`) and the operator allow-list
(`_WHERE_ANY_OPS = {=, !=, >, <, >=, <=, like, ilike}`) already existed and were
used by `having`, `where_any`, and `where_all` — `where`/`or_where` just never
parsed the string form.

## Fix

Added `_string_clause_predicate(clauses)`: when the first positional arg is a
`str`, parse the Laravel form and build a predicate; otherwise return `_UNSET`
so the existing expression/group/kwargs path runs unchanged.

- `where(col, value)` → `col == value`
- `where(col, operator, value)` → `_apply_operator(col, operator, value)`
- unknown operator → `ValueError` listing the valid set
- a lone string (`where("email")`) → `TypeError` with the expected shape

`where` and `_or_terms` (the engine behind `or_where`) both consult the helper,
so the string form ANDs/ORs onto the chain like every other clause. Expression,
callable-group, and kwargs forms are untouched (no existing test used the string
form on a model).

## Acceptance criteria

- `where("col", value)` filters by equality; `where("col", op, value)` applies
  the operator (`=`, `!=`, `>`, `<`, `>=`, `<=`, `like`, `ilike`).
- `or_where` accepts the same string forms and ORs them onto the chain.
- Unknown operator raises `ValueError`; a lone column string raises `TypeError`.
- Existing expression / group / kwargs forms still work.
- mypy, pyright, ruff clean; full database suite green.

## Out of scope (deferred)

- `<>` as an alias for `!=`, and `not like` / `not ilike` string operators —
  the canonical `_WHERE_ANY_OPS` set is shared with `having`/`where_any`;
  widening it is a separate parity pass.
- Array-of-conditions form `where([["a", 1], ["b", ">", 2]])`.

## Files

- `packages/arvel/src/arvel/database/query.py`
- `packages/arvel/tests/database/test_wi_025_where_string_operator.py` (new)
- `docs/site/docs/orm/query-builder.md`
