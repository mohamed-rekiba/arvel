# ADR-006 — Arvent — Schema & Migrations

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-24; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Schema DSL compiling to Alembic, migration runner, reversibility policy, partial indexes / NULLS NOT DISTINCT, JSONB type decorator, UUIDv7 from stdlib, order column via SELECT MAX.

## Why this is one ADR

Arvent's schema and migration story is one design: a Laravel-flavoured DSL that lowers to Alembic with consistent reversibility and PostgreSQL feature support. The seven ADRs explain the same migration runner from different angles.

---

## § 1 — Schema DSL compiles to Alembic ops (never raw SQL)

**Originally**: ADR-044 · Date: 2026-05-17

### Context

Laravel's `Schema::create("users", function($t) {...})` syntax is the
ergonomic peak of migration authoring. Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Raw SQL strings via `op.execute("CREATE TABLE ...")` | Trivial to implement | Dialect-specific; un-introspectable; SQLi by author error; breaks Alembic autogenerate diffs |
| B. **DSL compiles to Alembic op tree** | Dialect-agnostic; SQLA Column / Index / FK constraints introspectable | DSL helpers must be added one at a time; can't express every advanced feature |
| C. DSL compiles directly to SQLA Core | Faster path | Loses Alembic's history, branching, autogenerate, online-DDL helpers |

### Decision

Option B. Every `Blueprint` method records a `BlueprintOp` dataclass; the
compiler in `arvel.database.schema._compile` translates the op tree to one
of: SQLA `Column(...)`, `Index(...)`, `ForeignKey(...)` constraints for
`create_table`; or Alembic `op.add_column / op.alter_column /
op.create_index / op.create_foreign_key / op.rename_table` for `table`,
`rename`, etc.

**Raw SQL is forbidden in the DSL output**, including string-built `text()`
fragments. If a feature can't be expressed via these primitives, the helper
is rejected at code review.

### Consequences

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

---

## § 2 — Migration runner architecture

**Originally**: ADR-045 · Date: 2026-05-19

### Context

After `arvel migrate` / `migrate:rollback` / `migrate:status` and `arvel db:seed` declare `needs_application = True` and the entrypoint bootstraps the framework `Application` around them — but the actual `_run_*` methods are stubs. The README claims migrations are ✅ shipped. CLI review P0 #1 and the WI-021 ops report's FB-022-003 (high) both demand a real implementation now.

The question is **how**: pure-Alembic adoption, an Alembic-wrapped Arvel runner, or a from-scratch Migrator that uses SQLAlchemy directly.

### Decision

Ship a from-scratch `arvel.database.migrator.Migrator` that orchestrates user migration files directly against SQLAlchemy. Track applied migrations in a Laravel-style `migrations` table with an explicit `batch` column. Run each migration in its own transaction.

#### Specifics

1. **Migration file contract stays the same**: `async def up(schema)` / `async def down(schema)` module-level functions. `make:migration` already generates this shape; we don't churn the user's contract.

2. **Tracking table**: `migrations(id PK, migration UNIQUE, batch, applied_at)`. The `batch` column is the user-facing primitive — one `arvel migrate` invocation produces one batch; `migrate:rollback` undoes the last batch atomically.

3. **Per-migration transactions, not per-batch**: A failure inside migration M leaves migrations 1..M-1 applied (with their batch number) and stops. The next `arvel migrate` retries from M. This is Laravel's behavior.

4. **Migrator orchestrator is a free-standing class**: Constructor takes `(engine, migrations_path)`. No framework `Application` required. CLI commands resolve it at the boundary; tests instantiate it directly.

5. **Module loading**: `importlib.util.spec_from_file_location` with a unique per-file module name. After body executes, the entry is popped from `sys.modules` so repeated runs in the same Python process don't cache-poison.

### Alternatives considered

#### Alternative A — Pure Alembic adoption

Switch to Alembic-style migration scripts (top-level `upgrade(op)` and `downgrade(op)` functions with `op.create_table(...)` etc.) and let Alembic manage the version table.

**Why rejected**:
- Forces every existing Arvel user to rewrite migrations the moment we land it. Pre-alpha or not, the `make:migration` template has been the documented shape since WI-005.
- Alembic's `alembic_version` table tracks **one** head revision, not batches. `migrate:rollback` undoes one revision; there's no "undo the last batch I just applied" primitive. We'd lose Laravel parity on a foundational CLI command.
- Alembic's `env.py` ceremony, `alembic.ini`, and revision DAG management add complexity the user doesn't need for the 90% case of "linear migration history."

#### Alternative B — Wrap Alembic

Use Alembic as the runner but track our own `migrations` (with `batch`) table on top, so `migrate:rollback` semantics work.

**Why rejected**:
- Double bookkeeping — both `alembic_version` and `migrations` need to stay consistent. Race conditions and partial-failure recovery get hard fast.
- Doesn't solve the file-shape mismatch (still need to convert async `up(schema)` into Alembic's sync `upgrade(op)`).
- Net cost > net benefit; we'd inherit Alembic's edge cases without using its strengths.

#### Alternative C — Per-batch transactions

Wrap an entire `arvel migrate` invocation in a single transaction. Failure rolls back all migrations in the batch.

**Why rejected**:
- Laravel doesn't do this. Operators rely on "the migrations that succeeded committed; the next run retries from where I stopped."
- DDL statements in many databases (notably MySQL) can't be rolled back even inside a transaction — so per-batch atomicity is a lie on MySQL. Per-migration honesty beats per-batch fiction.
- A 50-migration first-time-deploy that fails on the last migration would lose 49 successful migrations. Operators would hate this.

#### Alternative D — Class-based migrations (subclass of `arvel.database.Migration`)

The existing `arvel.database.Migration` ABC (introduced in WI-003) requires class-based migrations with reversibility checks at `__init_subclass__` time. We could require all migrations to be subclasses.

**Why rejected**:
- The `make:migration` template generates **module-level async functions**, not classes. Users already have migrations in the function shape.
- The `Migration` class's `__init_subclass__` reversibility check is opinionated — it raises `MigrationNotReversibleError` if `up()` calls a destructive op and `down()` is empty. Useful for code review, harmful for one-off truncation migrations.
- We can keep the `Migration` ABC available for users who *want* the safety net, without making it mandatory.

### Consequences

#### Positive

- The four stub commands ship as real, working commands. Closes the most damaging CLI-review finding.
- Backwards-compatible with the existing `make:migration` file template — no user migration files need rewriting.
- Migrator is unit-testable in isolation (no framework bootstrap needed for tests).
- Batch semantics enable real-world rollback workflows (hot-fix a bad deploy by undoing just the last batch).
- Per-migration transactions keep retry incremental — operators can fix the failing migration and re-run without losing earlier progress.

#### Negative

- A user with a pre-existing `migrations` table from another tool (Flyway, manual SQL) will collide on table name. Documented in DXD-022.
- Alembic remains a declared dep but is no longer used by the framework. We accept the dependency cost (it's lightweight and downstream user projects may still want it) rather than removing it and breaking those users.
- DDL in transactions is a per-dialect minefield. We make a best-effort wrap but document that some DBs (MySQL prior to 8.0 with `atomic_ddl=off`) won't honor the transaction boundary for schema changes.

#### Neutral

- `arvel.database.Migration` class ABC stays; users can opt into reversibility-checked class-based migrations alongside the default function-based ones. The runner detects which form a file uses and dispatches accordingly. (Future-proof; this WI ships function-based only.)

### Out of scope

- `migrate:fresh`, `migrate:refresh`, `migrate:reset`, `db:wipe`. Tracked as carry-forward.
- Multi-database migrations (one connection only).
- `--pretend` mode that prints the SQL (only `--dry-run` for "would run" list).
- Migration squashing.

---

## § 3 — Migration reversibility enforced at registration time

**Originally**: ADR-046 · Date: 2026-05-17

### Context

Irreversible migrations are a production-day-one footgun. A developer drops a
column in `up()` and leaves `down()` empty, and the team discovers it only
when a rollback fails at 3 AM.

Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Trust developers — no enforcement | Zero overhead | The 3 AM scenario |
| B. Enforce at apply time (`migrate` refuses irreversible) | Catches before damage | Late — the migration is already merged to main; rollback path is broken in CI |
| C. **Enforce at registration time** (file load) | Catches at the unit test boundary; CI rejects merge | Slightly trickier — we have to introspect the `up()` callable |

### Decision

Option C. When the migration runtime loads a `Migration` subclass file:

1. Parse `up()`'s AST.
2. Walk for calls to `Schema.drop`, `Schema.drop_if_exists`, or any `.drop_column(...)`.
3. If found:
   - Parse `down()`'s AST.
   - If `down()` is empty (only `pass` or only a docstring), raise
     `MigrationNotReversibleError` at registration time.
   - If `down()` has at least one statement, accept (we trust the author wrote
     a real reverse; we don't try to prove semantic equivalence).

The check is purely structural — we don't validate the reverse is correct,
only that the author wrote *something*. Real semantic reversibility is
enforced by the test in `tests/database/test_migration_reversibility.py`,
which applies and rolls back every committed migration against an in-memory
SQLite during CI.

### Consequences

**Positive**:
- Drops without downs are caught at the pytest collection stage — instant
  feedback in the developer's editor.
- Combined with the CI apply-then-rollback test, the team gets two layers of
  defense: structural (registration) + semantic (test).
- Zero runtime overhead in production (the check runs at module import,
  which is once per process).

**Negative**:
- AST introspection of `up()` adds a small import-time cost. Migrations are
  imported lazily (only when `migrate` runs in production, or during the
  apply-then-rollback test in CI), so this is acceptable.
- A `down()` that does literally nothing meaningful (e.g. just a print
  statement) will pass the structural check. The semantic test in CI catches
  it on the rollback attempt.

**Enforcement**:
- `tests/database/test_migration_reversibility.py` parses every committed
  migration, then applies+rolls back against in-memory SQLite.
- Migration runtime raises `MigrationNotReversibleError` on registration
  with a clear message naming the operation and the offending file.

---

## § 4 — Blueprint DSL — Expose Partial Index `where=`, `unique=`, and `NULLS NOT DISTINCT`

**Originally**: ADR-047 · Date: 2026-05-23

### Context

`Blueprint.index()` internally stores `(name, cols, unique)` tuples and calls
`executor.create_index(name, table, cols, unique=unique)`. Three capabilities that Alembic and
SQLAlchemy already support are silently dropped:

1. `postgresql_where` — partial index predicate.
2. `unique=True` — hardcoded to `False`.
3. `postgresql_nulls_not_distinct` on `UniqueConstraint`.

Discovered during /032 post-analysis: the `items` table carries full-table
`deleted_at` indexes despite every active-record query filtering `WHERE deleted_at IS NULL`.

---

### Decision

#### `Blueprint.indexes` repr change

```python
## Before
list[tuple[str, list[str], bool]]
## (name, cols, unique)

## After
list[tuple[str, list[str], bool, dict[str, Any]]]
## (name, cols, unique, extra_kw)
```

`extra_kw` is forwarded as `**extra_kw` to `executor.create_index()`. Currently the only key
placed there is `postgresql_where`; the `dict` keeps the API open for future dialect kwargs
without another repr change.

#### `Blueprint.index()` new signature

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

#### `Blueprint.uniques` repr change

```python
## Before
list[tuple[str, list[str]]]
## (name, cols)

## After
list[tuple[str, list[str], bool | None]]
## (name, cols, nulls_not_distinct)
```

`_emit_create` builds `pg_kw: dict[str, Any] = {}` and populates
`pg_kw["postgresql_nulls_not_distinct"] = nnd` only when `nnd is not None`.

#### `Blueprint.unique()` new signature

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

### Alternatives Considered

**A. Separate `partial_index()` helper** — adds API surface with no benefit over a kwarg.
Rejected.

**B. Raw SQL via `executor.execute(text("CREATE INDEX ..."))` in migrations** — bypasses the
DSL entirely; every author needs to remember the escape hatch. Rejected.

**C. Dialect-agnostic `where_clause` string** — loses SQLAlchemy parameterisation safety.
Rejected.

---

### Consequences

- All new parameters are keyword-only with backward-compatible defaults → zero regression.
- Future dialect-specific index kwargs (e.g. `postgresql_include` for covering indexes) can
  be added to `extra_kw` without a further repr change.
- `NULLS NOT DISTINCT` requires PostgreSQL 15+ and SQLAlchemy ≥ 2.0.16. Arvel already
  requires SA 2.x; the PG version is the caller's responsibility.

---

## § 5 — `Blueprint.jsonb()` via TypeDecorator

**Originally**: ADR-048 · Date: 2026-05-24

### Context

The Schema DSL's `Blueprint.json()` emits `JSON`, but PostgreSQL `JSONB` is required for GIN
indexes and containment queries. Migrations needing JSONB had to import from
`sqlalchemy.dialects.postgresql` directly, coupling migration files to a specific dialect.

### Decision

Add a `_JsonB` TypeDecorator that emits `JSONB` on PostgreSQL and degrades to `JSON` on all
other dialects. Expose it as `Blueprint.jsonb(name)`. Follow the identical pattern used by
`_TsVector` in the same file.

### Consequences

- Positive: Migration files stay dialect-neutral. GIN indexing of JSONB columns is idiomatic.
- Positive: `_TsVector` pattern is proven in production — `_JsonB` reuses without invention.
- Negative: None. `Blueprint.json()` is unchanged; `jsonb()` is purely additive.

---

## § 6 — Use uuid.uuid7 from stdlib Instead of Custom Implementation

**Originally**: ADR-049 · Date: 2026-05-24

### Context

`arvel-ecommerce-demo/backend/app/models/base.py` contained a manual 32-line bit-twiddling
implementation of UUID v7 (timestamp-prefixed, RFC 9562). Python 3.14 ships `uuid.uuid7`
in the standard library, which is correct, RFC 9562 compliant, and monotonically sortable.

### Decision

Delete the custom implementation. Export `uuid7 = uuid.uuid7` from `app/models/base.py`
so all five model files that import `from app.models.base import uuid7` continue to work
without any changes to their `default_factory=uuid7` call sites.

### Consequences

- 32 lines of non-trivial bit manipulation removed from the codebase
- UUID generation is now handled by a stdlib function maintained by CPython
- `time`, `os` imports in `base.py` are removed (no longer needed)
- `import uuid` stays but `uuid.uuid7` is now a re-export rather than a replacement

---

## § 7 — order_column assigned via SELECT MAX + 1

**Originally**: ADR-050 · Date: 2026-05-24

### Context

`order_column` on the `media` table controls retrieval order within a collection.
requires it to be auto-assigned on insert. We need a strategy that works
without adding a DB sequence or trigger.

### Decision

Assign `order_column = SELECT MAX(order_column) + 1` scoped to `(model_type, model_id,
collection_name)` within the same ORM session, immediately before `Media.create()`.

### Consequences

- Simple; no migration needed (column already exists).
- Not safe for concurrent inserts from multiple workers. Under the framework's typical
  single-async-task-per-request model this is acceptable.
- If two concurrent inserts race, both may get the same `order_column`. Acceptable —
  `id` ASC is the tiebreaker and the order is still deterministic.
- Documented limitation; not a defect.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-044 | 2026-05-17 | Schema DSL compiles to Alembic ops (never raw SQL) | § 1 |
| ADR-045 | 2026-05-19 | Migration runner architecture | § 2 |
| ADR-046 | 2026-05-17 | Migration reversibility enforced at registration time | § 3 |
| ADR-047 | 2026-05-23 | Blueprint DSL — Expose Partial Index `where=`, `unique=`, and `NULLS NOT DISTINCT` | § 4 |
| ADR-048 | 2026-05-24 | `Blueprint.jsonb()` via TypeDecorator | § 5 |
| ADR-049 | 2026-05-24 | Use uuid.uuid7 from stdlib Instead of Custom Implementation | § 6 |
| ADR-050 | 2026-05-24 | order_column assigned via SELECT MAX + 1 | § 7 |
