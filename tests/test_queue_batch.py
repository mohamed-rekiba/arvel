"""Queues (doc 12/18) — Bus.batch(): job_batches tracking, then/catch/finally, progress/cancel,
allow_failures, and atomic counters under concurrent completion (the CAS retry loop in
`arvel.queue.batch`, not a plain read-modify-write)."""

from __future__ import annotations

import asyncio
from typing import Any

import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import Bus, Job, QueueManager
from arvel.queue.batch import Batch, JobBatch, apply_job_outcome

ORDER: list[str] = []
THEN_CALLS: list[Any] = []
CATCH_CALLS: list[Any] = []
FINALLY_CALLS: list[Any] = []


class Ok(Job):
    def __init__(self, label: str) -> None:
        self.label = label

    async def handle(self) -> None:
        ORDER.append(self.label)


class Boom(Job):
    tries = 1  # fail on the first (and only) attempt -> exhausted immediately

    async def handle(self) -> None:
        raise ValueError("boom")

    async def failed(self, exc: BaseException) -> None:
        """Silence: this test asserts on catch/counts, not FailedJob persistence noise."""


def _record_then(batch: Any) -> None:
    THEN_CALLS.append(batch.id)


def _record_catch(batch: Any, exc: BaseException) -> None:
    CATCH_CALLS.append((batch.id, type(exc)))


def _record_finally(batch: Any) -> None:
    FINALLY_CALLS.append(batch.id)


async def _manager() -> tuple[QueueManager, ConnectionResolver]:
    # await_inplace=True: each `push_instance()` runs its job fully (worker + bookkeeping) before
    # returning, so a batch's sequential dispatch loop settles deterministically, no polling.
    # `JobBatch` gets its own model-level connection, never bound as the app's "db" — so a `Boom`
    # job's exhaustion doesn't also try to persist a `FailedJob` (no `failed_jobs` table here).
    app = Application()
    db = ConnectionResolver()
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    JobBatch.set_connection(db)
    await db.execute(sa.schema.CreateTable(JobBatch.__table__))
    return manager, db


def _clear() -> None:
    ORDER.clear()
    THEN_CALLS.clear()
    CATCH_CALLS.clear()
    FINALLY_CALLS.clear()


async def test_then_fires_once_all_succeed_with_full_progress() -> None:
    _clear()
    manager, db = await _manager()
    try:
        batch = await (
            Bus.batch([Ok("a"), Ok("b"), Ok("c")])
            .then(_record_then)
            .finally_(_record_finally)
            .dispatch(manager=manager)
        )
        assert ORDER == ["a", "b", "c"]
        assert await batch.progress() == 100.0
        assert await batch.finished() is True
        assert await batch.cancelled() is False
        assert len(THEN_CALLS) == 1
        assert len(FINALLY_CALLS) == 1
    finally:
        set_application(None)
        await db.dispose()


async def test_failure_triggers_catch_and_cancels_remaining_jobs() -> None:
    _clear()
    manager, db = await _manager()
    try:
        batch = await (
            Bus.batch([Ok("a"), Boom(), Ok("c")])
            .then(_record_then)
            .catch(_record_catch)
            .finally_(_record_finally)
            .dispatch(manager=manager)
        )
        assert ORDER == ["a"]  # "c" never runs — the batch was cancelled before its turn
        assert await batch.cancelled() is True
        assert len(CATCH_CALLS) == 1
        assert CATCH_CALLS[0][1] is ValueError
        assert THEN_CALLS == []  # a disallowed failure cancelled the batch — `then` never fires
        assert len(FINALLY_CALLS) == 1  # `finally` always fires, exactly once
        counts = await batch.counts()
        assert counts == {"total": 3, "pending": 0, "failed": 1, "processed": 3}
    finally:
        set_application(None)
        await db.dispose()


async def test_allow_failures_lets_the_batch_finish() -> None:
    _clear()
    manager, db = await _manager()
    try:
        batch = await (
            Bus.batch([Ok("a"), Boom(), Ok("c")])
            .then(_record_then)
            .catch(_record_catch)
            .finally_(_record_finally)
            .allow_failures()
            .dispatch(manager=manager)
        )
        assert ORDER == ["a", "c"]  # "c" still runs — the batch was never cancelled
        assert await batch.cancelled() is False
        assert CATCH_CALLS == []  # allow_failures: catch never fires
        assert len(THEN_CALLS) == 1  # then still fires once every job has settled
        assert len(FINALLY_CALLS) == 1
        counts = await batch.counts()
        assert counts == {"total": 3, "pending": 0, "failed": 1, "processed": 3}
    finally:
        set_application(None)
        await db.dispose()


async def test_progress_and_cancel_handle() -> None:
    db = ConnectionResolver()
    JobBatch.set_connection(db)
    await db.execute(sa.schema.CreateTable(JobBatch.__table__))
    try:
        options = {"then": [], "catch": [], "finally": [], "name": None, "allow_failures": False}
        row = await JobBatch.create(
            total_jobs=4,
            pending_jobs=4,
            failed_jobs=0,
            options=options,
            cancelled_at=None,
            created_at=0,
            finished_at=None,
        )
        batch = Batch(row.id)
        assert await batch.progress() == 0.0
        assert await batch.finished() is False
        await apply_job_outcome(row.id, None)
        assert await batch.progress() == 25.0
        assert await batch.cancelled() is False
        await batch.cancel()
        assert await batch.cancelled() is True
        await batch.cancel()  # idempotent — no error, still cancelled
        assert await batch.cancelled() is True
    finally:
        await db.dispose()


async def test_concurrent_completions_do_not_lose_a_decrement() -> None:
    """The correctness point: two (here, five) jobs settling at the same moment via
    `asyncio.gather` must land on `pending_jobs == 0`, not a stale/lost decrement."""
    db = ConnectionResolver()
    JobBatch.set_connection(db)
    await db.execute(sa.schema.CreateTable(JobBatch.__table__))
    try:
        options = {"then": [], "catch": [], "finally": [], "name": None, "allow_failures": True}
        row = await JobBatch.create(
            total_jobs=5,
            pending_jobs=5,
            failed_jobs=0,
            options=options,
            cancelled_at=None,
            created_at=0,
            finished_at=None,
        )
        await asyncio.gather(*(apply_job_outcome(row.id, None) for _ in range(5)))
        fresh = await JobBatch.find(row.id)
        assert fresh is not None
        assert fresh.pending_jobs == 0
        assert fresh.finished_at is not None
    finally:
        await db.dispose()
