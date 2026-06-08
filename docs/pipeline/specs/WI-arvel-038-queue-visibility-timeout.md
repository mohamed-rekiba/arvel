# WI-arvel-038 — Database queue deletes jobs on pop; a worker crash loses the job

- **Module:** 38 (queue)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

## Audit scope

`arvel/queue/` — the database driver (`drivers/database.py`), the worker loop
(`worker.py`), the envelope (`envelope.py`), queue config (`config.py`), and the
`jobs` table migration (`migrations/create_jobs_table.py`).

## Findings

**Defect (fixed): delete-on-pop loses jobs on worker crash (F2).** The database
driver deleted the row inside `pop_blocking` the moment it handed an envelope to the
worker. If the worker then died mid-handle — OOM, `SIGKILL`, node eviction — the job
was already gone from the table and never ran. Laravel's database queue reserves a job
(`reserved_at`) and deletes it only after the handler completes; an unacked reservation
becomes visible again after `retry_after`. Arvel had no reservation, no visibility
timeout, and no redelivery: at-most-once with a silent-loss window.

Worker *cancellation* (graceful restart, `SIGINT`) was already handled correctly
(WI-008) — the in-flight job is re-pushed. The gap was specifically an abrupt crash
between pop and ack.

## Fix

Reserve-then-ack on the database driver:

- `jobs` gains a nullable `reserved_at` (bigint epoch). Migration updated.
- `pop_blocking` selects rows that are unreserved **or** whose `reserved_at` is older
  than `now - retry_after`, stamps `reserved_at = now` instead of deleting, and stashes
  the row id on `envelope.receipt` (transient, not serialized).
- `Worker._process_one` calls `conn.delete_reserved(envelope)` after the job is fully
  handled (succeeded, retried, or DLQ'd). A `CancelledError` skips the delete so the
  reservation lapses and the job redelivers — consistent with WI-008.
- Malformed payloads and unknown job classes are deleted outright (they can never run),
  so they don't sit reserved forever.
- `DatabaseQueueConfig.retry_after` (default 90s, env `QUEUE_DATABASE_RETRY_AFTER`)
  sets the visibility timeout. `delete_reserved` is duck-typed, so the redis/taskiq/sync
  drivers (which don't reserve) are untouched.

This makes the database driver at-least-once: a crash at the wrong moment can redeliver
a job that already ran, so handlers should be idempotent. Documented in the queue guide.

## Tests

`packages/arvel/tests/test_queue/drivers/test_database.py`:
- `test_pop_reserves_then_delete_reserved_removes_row` — pop reserves (row still
  counted, second pop returns None); `delete_reserved` removes it.
- `test_reservation_lapses_after_retry_after` — a reserved row whose worker never acked
  is reclaimable once the clock advances past `retry_after`.

`test_database_connection_sql_integration.py`: `jobs` DDL gains `reserved_at` so the
Postgres + MariaDB integration suite exercises the real reserve/redeliver path.

## Deferred (parity-additive, low value)

- `reserved_at`-based metrics (count of in-flight vs available) for `queue:size`.
- Per-job `retry_after` override (Laravel reads it off the job, not just the connection).

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors/0 warnings;
full queue suite 233 passed (incl. postgres/mysql integration); worker suite green.
