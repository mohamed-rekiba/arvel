# WI-arvel-037 — migrate:fresh / migrate:refresh leak a raw traceback when the DB is down

- **Module:** 37 (migrations / console)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

## Audit scope

`arvel/database/migrator.py` (Migrator: ensure_table, applied, pending, upgrade,
rollback, reset, drop_all, status) and the console commands (`migrate`,
`migrate:rollback`, `migrate:status`, `migrate:fresh`, `migrate:refresh`,
`migrate:reset`).

## Findings

The Migrator core is sound and well-covered: per-migration transactions (a body
failure leaves earlier migrations applied), one batch per `upgrade` run, rollback
limited to the last batch, fresh's dependency-aware drop order (mat views → tables
CASCADE → enum types), the sync/async body bridge, and non-destructive discovery
(`pending`/`status` never import files). No defect there.

**Defect (fixed): inconsistent DB-availability handling.** `migrate` pre-flights the
connection with `check_database_connection()` and maps `DatabaseUnavailableError` to
exit 2 with a friendly message. `migrate:fresh` and `migrate:refresh` did neither —
they went straight to `drop_all()` / `reset()`. Against a down or unreachable DB they
raised a raw SQLAlchemy error that their `except` clauses (MigrationFailedError /
MigrationFileInvalidError / BootstrapFailedError) didn't catch, so the CLI dumped a
traceback and exited 1 instead of the intended 2 (A10 — mishandling of exceptional
conditions, raw internals leaked).

## Fix

Both destructive commands now call `check_database_connection(resolve_engine(app))`
before touching the schema, and their callbacks catch `DatabaseUnavailableError` →
`typer.Exit(code=2)` with the same "database is not available" message as `migrate`.

## Tests

`packages/arvel/tests/console/test_migrate_reset_family.py` (+2): parametrized over
fresh/refresh, monkeypatch the health check to raise `DatabaseUnavailableError` and
assert exit code 2 + the friendly message.

## Deferred (parity-additive, low value)

- `migrate --step` (record each migration as its own batch) and
  `migrate:rollback --step=N` (roll back N batches).
- `migrate:status` doesn't list a migration that was applied but whose file was later
  deleted (Laravel shows it as ran).
- SQLite batch-mode (`render_as_batch`) for column alter/drop migrations.

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors/0 warnings;
reset-family suite 11 passed; migrator unit suite green.
