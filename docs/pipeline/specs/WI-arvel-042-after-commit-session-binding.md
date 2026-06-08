# WI-arvel-042 — DatabaseTransaction fires after-commit callbacks while the committed session is still active

- **Module:** 42 (DB transactions / connections — `DB`, `DatabaseTransaction`)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

## Audit scope

The two transaction surfaces and their after-commit machinery:
`arvel/database/db.py` (`DB.transaction`, `DB.transactional`, the imperative
`begin_transaction`/`commit`/`rollback` stack, `DB.autocommit`, `DB.after_commit`,
`DB.pretend`, raw `select`/`scalar`/`statement`, `is_retryable_db_error`,
query-log capture) and `arvel/http/middleware/database_transaction.py`
(`DatabaseTransaction`), plus the after-commit queue in `arvel/database/session.py`.

## Findings

Most of the surface is sound and Laravel-aligned:

- `DB.transaction()` is reentrant via savepoints; the outermost frame owns the
  after-commit queue and fires callbacks only on commit, **after** the session is
  closed and the active-session contextvar is reset. `transactional()` retries
  only on deadlock/serialization (`is_retryable_db_error` — SQLSTATE 40001/40P01
  + driver-message tokens). The imperative stack tears down cleanly (savepoint
  commit/rollback releases nothing else; outermost commit fires callbacks).
- `DB.autocommit()` yields an independent `AUTOCOMMIT` connection and leaves the
  caller's session untouched — correct for `REFRESH MATERIALIZED VIEW
  CONCURRENTLY` / `CREATE INDEX CONCURRENTLY`. `DB.pretend()` rolls back. Raw SQL
  uses bound params (no injection). `after_commit` raises outside a transaction.

**Defect (fixed): the HTTP middleware fired callbacks with the committed session
still bound.** `DatabaseTransaction._run` ran the callback loop in the `else`
branch, *inside* the `async with maker() as session:` block — so callbacks fired
after the `session.begin()` COMMIT but before `reset_active_session` (which sat in
the `finally`). A callback doing an ORM write through the active session
(`await Model.create(...)`) would open a fresh implicit transaction on the
about-to-close session; SQLAlchemy rolls that back on close, so the write was
**silently discarded** (A10 — mishandling of exceptional conditions). It also
diverged from `DB.transaction()`, which fires callbacks after the session is closed
and unbound. The kit's only after-commit user calls `DB.autocommit()` internally
(independent connection), so the bug was latent — but the footgun is real for any
callback that touches the DB via the active session.

## Fix

Restructure `DatabaseTransaction._run` to fire callbacks **after** the
`async with maker() as session:` block exits and the active session is reset —
identical to `DB.transaction()`:

- track `committed` inside the block; `_ResponseRollback` still returns the
  response with `committed` false (callbacks skipped on 4xx/5xx);
- after the block, `if committed:` run the callback loop, then return the response.

With no active session bound, a callback that touches the DB opens its own
transaction instead of writing into the closed one.

## Tests

`packages/arvel/tests/http/test_database_transaction_middleware.py`:
- `test_after_commit_callbacks_run_with_no_active_session` — a callback registered
  via `DB.after_commit` runs after commit and observes `get_optional_session() is
  None` (parity with `DB.transaction()`).
- `test_after_commit_callbacks_skipped_on_rollback` — a 4xx response rolls back and
  the callback never fires.

## Deferred (parity-additive / separate items)

- Per-savepoint after-commit scoping: a callback registered inside a nested
  `DB.transaction()` / `begin_transaction()` savepoint that later rolls back still
  fires at the outer commit (it lives on the outer queue). Laravel's
  `DatabaseTransactionsManager` discards callbacks for a rolled-back level. Edge
  case; tracked, not fixed here.
- After-commit callback exceptions abort the remaining callbacks (same in both
  paths) — matches a simple sequential model; Laravel has no stronger guarantee.

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors / 0
warnings; transaction middleware + db edge/imperative suites 42 passed (incl. 2
new); full http + database suites 1348 passed.
