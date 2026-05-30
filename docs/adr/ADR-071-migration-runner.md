# ADR-071 — Migration runner architecture

**Status**: Accepted
**Date**: 2026-05-19
**SAD**: `docs/architecture/SAD-022-real-migrator.md`

---

## Context

After `arvel migrate` / `migrate:rollback` / `migrate:status` and `arvel db:seed` declare `needs_application = True` and the entrypoint bootstraps the framework `Application` around them — but the actual `_run_*` methods are stubs. The README claims migrations are ✅ shipped. CLI review P0 #1 and the WI-021 ops report's FB-022-003 (high) both demand a real implementation now.

The question is **how**: pure-Alembic adoption, an Alembic-wrapped Arvel runner, or a from-scratch Migrator that uses SQLAlchemy directly.

## Decision

Ship a from-scratch `arvel.database.migrator.Migrator` that orchestrates user migration files directly against SQLAlchemy. Track applied migrations in a Laravel-style `migrations` table with an explicit `batch` column. Run each migration in its own transaction.

### Specifics

1. **Migration file contract stays the same**: `async def up(schema)` / `async def down(schema)` module-level functions. `make:migration` already generates this shape; we don't churn the user's contract.

2. **Tracking table**: `migrations(id PK, migration UNIQUE, batch, applied_at)`. The `batch` column is the user-facing primitive — one `arvel migrate` invocation produces one batch; `migrate:rollback` undoes the last batch atomically.

3. **Per-migration transactions, not per-batch**: A failure inside migration M leaves migrations 1..M-1 applied (with their batch number) and stops. The next `arvel migrate` retries from M. This is Laravel's behavior.

4. **Migrator orchestrator is a free-standing class**: Constructor takes `(engine, migrations_path)`. No framework `Application` required. CLI commands resolve it at the boundary; tests instantiate it directly.

5. **Module loading**: `importlib.util.spec_from_file_location` with a unique per-file module name. After body executes, the entry is popped from `sys.modules` so repeated runs in the same Python process don't cache-poison.

## Alternatives considered

### Alternative A — Pure Alembic adoption

Switch to Alembic-style migration scripts (top-level `upgrade(op)` and `downgrade(op)` functions with `op.create_table(...)` etc.) and let Alembic manage the version table.

**Why rejected**:
- Forces every existing Arvel user to rewrite migrations the moment we land it. Pre-alpha or not, the `make:migration` template has been the documented shape since WI-005.
- Alembic's `alembic_version` table tracks **one** head revision, not batches. `migrate:rollback` undoes one revision; there's no "undo the last batch I just applied" primitive. We'd lose Laravel parity on a foundational CLI command.
- Alembic's `env.py` ceremony, `alembic.ini`, and revision DAG management add complexity the user doesn't need for the 90% case of "linear migration history."

### Alternative B — Wrap Alembic

Use Alembic as the runner but track our own `migrations` (with `batch`) table on top, so `migrate:rollback` semantics work.

**Why rejected**:
- Double bookkeeping — both `alembic_version` and `migrations` need to stay consistent. Race conditions and partial-failure recovery get hard fast.
- Doesn't solve the file-shape mismatch (still need to convert async `up(schema)` into Alembic's sync `upgrade(op)`).
- Net cost > net benefit; we'd inherit Alembic's edge cases without using its strengths.

### Alternative C — Per-batch transactions

Wrap an entire `arvel migrate` invocation in a single transaction. Failure rolls back all migrations in the batch.

**Why rejected**:
- Laravel doesn't do this. Operators rely on "the migrations that succeeded committed; the next run retries from where I stopped."
- DDL statements in many databases (notably MySQL) can't be rolled back even inside a transaction — so per-batch atomicity is a lie on MySQL. Per-migration honesty beats per-batch fiction.
- A 50-migration first-time-deploy that fails on the last migration would lose 49 successful migrations. Operators would hate this.

### Alternative D — Class-based migrations (subclass of `arvel.database.Migration`)

The existing `arvel.database.Migration` ABC (introduced in WI-003) requires class-based migrations with reversibility checks at `__init_subclass__` time. We could require all migrations to be subclasses.

**Why rejected**:
- The `make:migration` template generates **module-level async functions**, not classes. Users already have migrations in the function shape.
- The `Migration` class's `__init_subclass__` reversibility check is opinionated — it raises `MigrationNotReversibleError` if `up()` calls a destructive op and `down()` is empty. Useful for code review, harmful for one-off truncation migrations.
- We can keep the `Migration` ABC available for users who *want* the safety net, without making it mandatory.

## Consequences

### Positive

- The four stub commands ship as real, working commands. Closes the most damaging CLI-review finding.
- Backwards-compatible with the existing `make:migration` file template — no user migration files need rewriting.
- Migrator is unit-testable in isolation (no framework bootstrap needed for tests).
- Batch semantics enable real-world rollback workflows (hot-fix a bad deploy by undoing just the last batch).
- Per-migration transactions keep retry incremental — operators can fix the failing migration and re-run without losing earlier progress.

### Negative

- A user with a pre-existing `migrations` table from another tool (Flyway, manual SQL) will collide on table name. Documented in DXD-022.
- Alembic remains a declared dep but is no longer used by the framework. We accept the dependency cost (it's lightweight and downstream user projects may still want it) rather than removing it and breaking those users.
- DDL in transactions is a per-dialect minefield. We make a best-effort wrap but document that some DBs (MySQL prior to 8.0 with `atomic_ddl=off`) won't honor the transaction boundary for schema changes.

### Neutral

- `arvel.database.Migration` class ABC stays; users can opt into reversibility-checked class-based migrations alongside the default function-based ones. The runner detects which form a file uses and dispatches accordingly. (Future-proof; this WI ships function-based only.)

## Out of scope

- `migrate:fresh`, `migrate:refresh`, `migrate:reset`, `db:wipe`. Tracked as carry-forward.
- Multi-database migrations (one connection only).
- `--pretend` mode that prints the SQL (only `--dry-run` for "would run" list).
- Migration squashing.
