"""arvel.queue.batch — job batches: `job_batches` tracking + the `Batch` handle (`Bus::batch()`).

`JobBatch` is the DB row (the scaffold ships its migration); counter updates (`pending_jobs`/
`failed_jobs`) are a single **atomic `UPDATE ... SET pending_jobs = pending_jobs - 1`** — the DB
does the arithmetic, so two jobs finishing at the same moment never lose a decrement, without an
app-space read-modify-write or a DB-specific `RETURNING` clause. The exactly-once batch lifecycle
transitions (`cancel`/`finish`) stay guarded by `WHERE <ts> IS NULL`. Kept in its own module so
importing `arvel.queue` doesn't pull in `arvel.database` (mirrors `queue/jobs.py`/`queue/failed.py`).
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

from arvel.database import HasUuids, Model


class JobBatch(HasUuids, Model):
    """A batch's row: `total_jobs`/`pending_jobs`/`failed_jobs` counters, its `options` (the
    then/catch/finally callback refs + name + allow_failures — set once at creation, never
    mutated), and `cancelled_at`/`finished_at` (unix timestamps, `None` until each happens)."""

    __table_name__ = "job_batches"
    __timestamps__: ClassVar[bool] = False  # created_at/finished_at are explicit unix-ts columns
    __fields__: ClassVar[dict[str, Any]] = {
        "total_jobs": int,
        "pending_jobs": int,
        "failed_jobs": int,
        "options": dict,
        "cancelled_at": int,
        "created_at": int,
        "finished_at": int,
    }
    __fillable__: ClassVar[list[str]] = [
        "total_jobs",
        "pending_jobs",
        "failed_jobs",
        "options",
        "cancelled_at",
        "created_at",
        "finished_at",
    ]
    __casts__: ClassVar[dict[str, Any]] = {"options": "json"}

    # dynamic columns (stored in _attributes) — annotated so the type checker accepts assignment
    total_jobs: Any
    pending_jobs: Any
    failed_jobs: Any
    options: Any
    cancelled_at: Any
    finished_at: Any

    def progress(self) -> float:
        """Percent of jobs processed (0..100) — 100 for an empty batch."""
        total = int(self.total_jobs)
        if not total:
            return 100.0
        processed = total - int(self.pending_jobs)
        return (processed / total) * 100

    def finished(self) -> bool:
        return self.finished_at is not None

    def cancelled(self) -> bool:
        return self.cancelled_at is not None

    def counts(self) -> dict[str, int]:
        return {
            "total": self.total_jobs,
            "pending": self.pending_jobs,
            "failed": self.failed_jobs,
            "processed": self.total_jobs - self.pending_jobs,
        }


class Batch:
    """A dispatched batch's live handle — every accessor
    re-fetches the row, so it always reflects the latest counters (a batch is mutated from worker
    processes this handle never sees)."""

    def __init__(self, batch_id: str) -> None:
        self.id = batch_id

    async def _row(self) -> JobBatch:
        return await JobBatch.find_or_fail(self.id)

    async def total_jobs(self) -> int:
        return int((await self._row()).total_jobs)

    async def pending_jobs(self) -> int:
        return int((await self._row()).pending_jobs)

    async def failed_jobs(self) -> int:
        return int((await self._row()).failed_jobs)

    async def progress(self) -> float:
        return (await self._row()).progress()

    async def finished(self) -> bool:
        return (await self._row()).finished()

    async def cancelled(self) -> bool:
        return (await self._row()).cancelled()

    async def counts(self) -> dict[str, int]:
        return (await self._row()).counts()

    async def cancel(self) -> None:
        """Mark the batch cancelled (idempotent) — remaining queued jobs no-op instead of running
        (see `is_batch_cancelled`, checked by `QueueManager._invoke` before each batched job)."""
        await _cancel_batch_once(self.id)


async def is_batch_cancelled(batch_id: str) -> bool:
    """Whether `batch_id` is already cancelled — checked before running a batched job so the rest
    of a cancelled batch's queued jobs no-op instead of executing."""
    row = await JobBatch.find(batch_id)
    return row is not None and row.cancelled_at is not None


async def _record_job_outcome(batch_id: str, *, failed: bool) -> JobBatch:
    """Atomically apply one job's outcome to its batch's counters: decrement `pending_jobs`,
    and on a failure also increment `failed_jobs`.

    One atomic `UPDATE ... SET pending_jobs = pending_jobs - 1` — the DB does the arithmetic, so
    two jobs settling at the same moment each land their own decrement with no read-modify-write in
    app space (a compare-and-swap retry loop here was flaky: it relied on `rowcount` behaving as a
    lock, which a shared SQLite connection under `asyncio.gather` doesn't guarantee). Re-read after
    for the post-decrement counts — they may reflect a concurrent job's decrement too, which is
    fine: the caller that lands the final decrement always re-reads `pending_jobs <= 0`, and the
    guarded `_finish_batch_once` makes the finish transition fire exactly once regardless.
    """
    columns = JobBatch.__table__.c
    delta = 1 if failed else 0
    await JobBatch.where("id", "=", batch_id).update(
        {
            "pending_jobs": columns["pending_jobs"] - 1,
            "failed_jobs": columns["failed_jobs"] + delta,
        }
    )
    return await JobBatch.find_or_fail(batch_id)


async def _cancel_batch_once(batch_id: str) -> bool:
    """Atomically mark the batch cancelled — `True` only for the caller that actually flips it (a
    guarded `UPDATE ... WHERE cancelled_at IS NULL`), so `catch` fires exactly once even if two
    jobs fail around the same moment."""
    claim = (
        await JobBatch.where("id", "=", batch_id)
        .where_null("cancelled_at")
        .update({"cancelled_at": int(time.time())})
    )
    return claim.rowcount == 1


async def _finish_batch_once(batch_id: str) -> bool:
    """Atomically stamp `finished_at` — `True` only for the caller that actually flips it, so
    `then`/`finally` fire exactly once even if the last two jobs settle at the same moment."""
    claim = (
        await JobBatch.where("id", "=", batch_id)
        .where_null("finished_at")
        .update({"finished_at": int(time.time())})
    )
    return claim.rowcount == 1


async def _run_callbacks(refs: list[str], *args: Any) -> None:
    import inspect

    from arvel.queue import _load  # pyright: ignore[reportPrivateUsage]

    for ref in refs:
        outcome = _load(ref)(*args)
        if inspect.isawaitable(outcome):
            await outcome


async def finalize_empty_batch(batch_id: str) -> None:
    """Finish a batch that was dispatched with zero jobs — no job will ever settle to trigger the
    normal transition, so `then`/`finally` fire here immediately (finalizes an empty batch
    right away)."""
    if not await _finish_batch_once(batch_id):
        return
    row = await JobBatch.find(batch_id)
    if row is None:
        return
    batch = Batch(batch_id)
    await _run_callbacks(row.options.get("then", []), batch)
    await _run_callbacks(row.options.get("finally", []), batch)


async def apply_job_outcome(batch_id: str, exc: BaseException | None) -> None:
    """The worker's bookkeeping hook, called once a batched job settles (success — `exc is None`
    — or exhausts its retries). Atomically updates the batch's counters and, on whichever
    transition actually finishes it, fires `then`/`catch`/`finally` exactly once each — no matter
    how many jobs settle at the same moment."""
    row = await JobBatch.find(batch_id)
    if row is None:  # the batch row is gone (shouldn't happen) — nothing to update
        return
    options = row.options
    allow_failures = bool(options.get("allow_failures"))
    updated = await _record_job_outcome(batch_id, failed=exc is not None)
    batch = Batch(batch_id)

    if exc is not None and not allow_failures and await _cancel_batch_once(batch_id):
        await _run_callbacks(options.get("catch", []), batch, exc)

    if updated.pending_jobs <= 0 and await _finish_batch_once(batch_id):
        if not await batch.cancelled():
            await _run_callbacks(options.get("then", []), batch)
        await _run_callbacks(options.get("finally", []), batch)


__all__ = [
    "Batch",
    "JobBatch",
    "apply_job_outcome",
    "is_batch_cancelled",
]
