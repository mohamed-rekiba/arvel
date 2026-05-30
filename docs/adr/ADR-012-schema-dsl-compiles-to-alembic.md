# ADR-012 — Schema DSL compiles to Alembic ops (never raw SQL)

**Status**: Accepted
**Date**: 2026-05-17

## Context

Laravel's `Schema::create("users", function($t) {...})` syntax is the
ergonomic peak of migration authoring. Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Raw SQL strings via `op.execute("CREATE TABLE ...")` | Trivial to implement | Dialect-specific; un-introspectable; SQLi by author error; breaks Alembic autogenerate diffs |
| B. **DSL compiles to Alembic op tree** | Dialect-agnostic; SQLA Column / Index / FK constraints introspectable | DSL helpers must be added one at a time; can't express every advanced feature |
| C. DSL compiles directly to SQLA Core | Faster path | Loses Alembic's history, branching, autogenerate, online-DDL helpers |

## Decision

Option B. Every `Blueprint` method records a `BlueprintOp` dataclass; the
compiler in `arvel.database.schema._compile` translates the op tree to one
of: SQLA `Column(...)`, `Index(...)`, `ForeignKey(...)` constraints for
`create_table`; or Alembic `op.add_column / op.alter_column /
op.create_index / op.create_foreign_key / op.rename_table` for `table`,
`rename`, etc.

**Raw SQL is forbidden in the DSL output**, including string-built `text()`
fragments. If a feature can't be expressed via these primitives, the helper
is rejected at code review.

## Consequences

**Positive**:
- Alembic's history table, branching, and autogenerate continue to work — we
  layer over Alembic, we don't replace it.
- Cross-dialect support (SQLite + Postgres + MySQL) is automatic where SQLA
  handles it; the DSL surface intentionally rejects helpers that don't have
  a portable SQLA representation.
- Migrations are introspectable as Python objects — testable in unit tests.

**Negative**:
- Advanced features (Postgres-specific `EXCLUDE`, MySQL `GENERATED ALWAYS AS`)
  require either a SQLA-level primitive or an explicit `op.execute(...)` inside
  a migration's `up()` body (outside the DSL — author opts in to dialect lock-in).
- We can't ship a feature until SQLA / Alembic does.

**Enforcement**:
- `tests/database/test_schema_dsl.py` asserts every DSL helper compiles to a
  SQLA-Column or Alembic-op equivalent.
- Code review: a PR adding a DSL helper that emits a raw SQL string is rejected.
