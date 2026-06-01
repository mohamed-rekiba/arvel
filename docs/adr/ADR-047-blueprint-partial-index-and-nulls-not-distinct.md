# ADR-047: Blueprint DSL — Expose Partial Index `where=`, `unique=`, and `NULLS NOT DISTINCT`

**Status**: Accepted
**Date**: 2026-05-23
**Supersedes**: None
**Related**: ADR-044 (Schema DSL compiles to Alembic)

---

## Context

`Blueprint.index()` internally stores `(name, cols, unique)` tuples and calls
`executor.create_index(name, table, cols, unique=unique)`. Three capabilities that Alembic and
SQLAlchemy already support are silently dropped:

1. `postgresql_where` — partial index predicate.
2. `unique=True` — hardcoded to `False`.
3. `postgresql_nulls_not_distinct` on `UniqueConstraint`.

Discovered during /032 post-analysis: the `items` table carries full-table
`deleted_at` indexes despite every active-record query filtering `WHERE deleted_at IS NULL`.

---

## Decision

### `Blueprint.indexes` repr change

```python
# Before
list[tuple[str, list[str], bool]]
# (name, cols, unique)

# After
list[tuple[str, list[str], bool, dict[str, Any]]]
# (name, cols, unique, extra_kw)
```

`extra_kw` is forwarded as `**extra_kw` to `executor.create_index()`. Currently the only key
placed there is `postgresql_where`; the `dict` keeps the API open for future dialect kwargs
without another repr change.

### `Blueprint.index()` new signature

```python
def index(
    self,
    columns: list[str] | str,
    *,
    name: str | None = None,
    unique: bool = False,
    where: Any = None,
) -> None:
```

`where=None` → no extra kwarg. `where=text(...)` → `extra_kw = {"postgresql_where": where}`.

### `Blueprint.uniques` repr change

```python
# Before
list[tuple[str, list[str]]]
# (name, cols)

# After
list[tuple[str, list[str], bool | None]]
# (name, cols, nulls_not_distinct)
```

`_emit_create` builds `pg_kw: dict[str, Any] = {}` and populates
`pg_kw["postgresql_nulls_not_distinct"] = nnd` only when `nnd is not None`.

### `Blueprint.unique()` new signature

```python
def unique(
    self,
    columns: list[str] | str,
    *,
    name: str | None = None,
    nulls_not_distinct: bool | None = None,
) -> None:
```

---

## Alternatives Considered

**A. Separate `partial_index()` helper** — adds API surface with no benefit over a kwarg.
Rejected.

**B. Raw SQL via `executor.execute(text("CREATE INDEX ..."))` in migrations** — bypasses the
DSL entirely; every author needs to remember the escape hatch. Rejected.

**C. Dialect-agnostic `where_clause` string** — loses SQLAlchemy parameterisation safety.
Rejected.

---

## Consequences

- All new parameters are keyword-only with backward-compatible defaults → zero regression.
- Future dialect-specific index kwargs (e.g. `postgresql_include` for covering indexes) can
  be added to `extra_kw` without a further repr change.
- `NULLS NOT DISTINCT` requires PostgreSQL 15+ and SQLAlchemy ≥ 2.0.16. Arvel already
  requires SA 2.x; the PG version is the caller's responsibility.
