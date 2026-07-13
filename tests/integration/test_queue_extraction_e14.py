"""Integration (E14/DR-0048) — the V6 worker-loop/serialization extraction over a **real Postgres**
`jobs`/`failed_jobs`/`job_batches` schema (the consumer path: `QueueManager.work()` draining through
the split-out `JobWorker`), per the spec's proof plan:

1. `fail_on_timeout=True` fails a job on its **first** timeout — no retry.
2. `fail_on_timeout=False` (default) retries a timed-out job up to `tries`, exactly as before V6.
3. A chain and a batch each settle identically to pre-extraction behavior, run separately (proves
   the `_invoke`/`_runner` move preserved chain semantics and batch semantics on their own).
4. QA coverage gap close: ONE job that is simultaneously a batch member, a chain head, AND unique —
   the top design risk (`_invoke`'s off-queue/batch/retry/chain/unique/worker-flag ordering) is only
   real when these interact on the same job, not when exercised separately as in (3).

Mirrors `tests/integration/test_amqp_queue.py`'s polling idiom; uses the in-memory broker (V6 is a
pure worker-loop/serialization restructure — the broker isn't what's under test here) with a real
Postgres-backed `jobs`/`failed_jobs`/`job_batches` schema, exactly as the AMQP suite's
retry-release/visibility-timeout tests do.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from taskiq import InMemoryBroker

from arvel.cache.provider import CacheServiceProvider
from arvel.database import ConnectionResolver
from arvel.kernel import Application, set_application
from arvel.queue import (  # pyright: ignore[reportPrivateUsage]
    Bus,
    FailedJob,
    Job,
    QueuedJob,
    QueueManager,
)
from arvel.queue.batch import JobBatch
from arvel.queue.middleware import ShouldBeUnique
from arvel.queue.serialization import serialize_instance

pytestmark = pytest.mark.integration


class SlowTimeoutFailFast(Job):
    """Never finishes inside `timeout`; `fail_on_timeout=True` -> failed on the first timeout."""

    tries = 3
    backoff = 0
    timeout = 0.2
    fail_on_timeout = True

    async def handle(self) -> None:
        await asyncio.sleep(10)


class SlowTimeoutRetries(Job):
    """Same shape, `fail_on_timeout` left at its default `False` -> retried like any other failure."""

    tries = 2
    backoff = 0.2
    timeout = 0.1

    async def handle(self) -> None:
        await asyncio.sleep(10)


async def _setup(postgres_url: str) -> tuple[QueueManager, ConnectionResolver]:
    app = Application()
    db = ConnectionResolver({"default": {"url": postgres_url}})
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker())
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    FailedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    await db.execute(sa.schema.CreateTable(FailedJob.__table__))
    return manager, db


async def test_fail_on_timeout_true_fails_on_first_timeout_over_postgres(
    postgres_url: str,
) -> None:
    manager, db = await _setup(postgres_url)
    try:
        await manager.dispatch_after(0, SlowTimeoutFailFast())

        worker = asyncio.create_task(manager.work(release_interval=0.1))
        failed = None
        for _ in range(100):
            rows = await FailedJob.all()
            if rows:
                failed = rows
                break
            await asyncio.sleep(0.1)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert failed is not None and len(failed) == 1
        assert "TimeoutError" in failed[0].exception
        assert await QueuedJob.all() == []  # never released for a retry
    finally:
        with contextlib.suppress(Exception):
            await manager.broker.shutdown()
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(QueuedJob.__table__))
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(FailedJob.__table__))
        await db.dispose()
        set_application(None)


async def test_fail_on_timeout_false_retries_before_failing_over_postgres(
    postgres_url: str,
) -> None:
    manager, db = await _setup(postgres_url)
    try:
        await manager.dispatch_after(0, SlowTimeoutRetries())
        worker = asyncio.create_task(manager.work(release_interval=0.05))

        # attempt 1 times out -> released back to the jobs table with attempts bumped to 1 (not
        # failed outright) — the pre-worker row (attempts=0, from `dispatch_after`) doesn't count.
        released = None
        for _ in range(100):
            rows = await QueuedJob.all()
            if rows and rows[0].attempts == 1:
                released = rows
                break
            await asyncio.sleep(0.05)
        assert released is not None and released[0].attempts == 1

        # attempt 2 (tries=2) times out too -> now it's failed, exactly like a plain exception
        failed = None
        for _ in range(100):
            rows = await FailedJob.all()
            if rows:
                failed = rows
                break
            await asyncio.sleep(0.05)
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

        assert failed is not None and len(failed) == 1
        assert await QueuedJob.all() == []
    finally:
        with contextlib.suppress(Exception):
            await manager.broker.shutdown()
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(QueuedJob.__table__))
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(FailedJob.__table__))
        await db.dispose()
        set_application(None)


class ChainStep(Job):
    def __init__(self, path: str, label: str) -> None:
        self.path = path
        self.label = label

    async def handle(self) -> None:
        target = Path(self.path)
        existing = target.read_text() if target.exists() else ""
        target.write_text(existing + self.label)


class BatchStep(Job):
    def __init__(self, path: str, label: str) -> None:
        self.path = path
        self.label = label

    async def handle(self) -> None:
        Path(self.path).write_text(self.label)


async def test_chain_and_batch_settle_identically_after_the_v6_extraction_over_postgres(
    postgres_url: str, tmp_path: Path
) -> None:
    """Proves the `_invoke`/`_runner` move onto `JobWorker` preserved chain continuation + batch
    outcome tracking together (the top extraction risk — invisible unless both run for real)."""
    app = Application()
    db = ConnectionResolver({"default": {"url": postgres_url}})
    app.instance("db", db)
    # await_inplace=True: deterministic settling, no polling — mirrors test_queue_chain.py/
    # test_queue_batch.py's own pattern, now proven against a real Postgres-backed schema.
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    JobBatch.set_connection(db)
    await db.execute(sa.schema.CreateTable(JobBatch.__table__))
    try:
        chain_target = tmp_path / "chain.txt"
        await Bus.chain(
            [
                ChainStep(str(chain_target), "a"),
                ChainStep(str(chain_target), "b"),
                ChainStep(str(chain_target), "c"),
            ]
        ).dispatch(manager=manager)
        assert chain_target.read_text() == "abc"  # strict order preserved

        targets = [tmp_path / f"batch_{i}.txt" for i in range(3)]
        jobs: list[Any] = [BatchStep(str(t), f"job-{i}") for i, t in enumerate(targets)]
        batch = await Bus.batch(jobs).dispatch(manager=manager)

        assert await batch.finished()
        assert await batch.progress() == 100.0
        assert await batch.cancelled() is False
        assert all(target.exists() for target in targets)
    finally:
        with contextlib.suppress(Exception):
            await db.execute(sa.schema.DropTable(JobBatch.__table__))
        await db.dispose()
        set_application(None)


# --- QA gap close: ONE job that is a batch member AND a chain head AND unique ---------------
# The _invoke ordering (off-queue → batch-cancel → DI/middleware → retries → chain → batch
# outcome → unique-lock release → worker-flags) is only truly exercised when all three interact
# on the same job. These drive that on real Postgres, per QA's verified scenario.

_COMBO_RUN: list[str] = []
_COMBO_THEN: list[bool] = []
_COMBO_CATCH: list[bool] = []


def _combo_then(batch: object) -> None:
    _COMBO_THEN.append(True)


def _combo_catch(batch: object, exc: BaseException) -> None:
    _COMBO_CATCH.append(True)


class ComboTail(Job):
    def __init__(self, label: str) -> None:
        self.label = label

    async def handle(self) -> None:
        _COMBO_RUN.append(self.label)


class ComboHeadOk(ShouldBeUnique, Job):
    unique_for = 3600

    def __init__(self, uid: str) -> None:
        self.uid = uid

    def unique_id(self) -> str:
        return self.uid

    async def handle(self) -> None:
        _COMBO_RUN.append("head-ok")


class ComboHeadBoom(ShouldBeUnique, Job):
    unique_for = 3600
    tries = 1

    def __init__(self, uid: str) -> None:
        self.uid = uid

    def unique_id(self) -> str:
        return self.uid

    async def handle(self) -> None:
        _COMBO_RUN.append("head-boom")
        raise RuntimeError("combo head failed")


async def _combo_manager(postgres_url: str) -> tuple[QueueManager, ConnectionResolver]:
    app = Application()
    CacheServiceProvider(app).register()  # ShouldBeUnique needs the cache-backed lock
    db = ConnectionResolver({"default": {"url": postgres_url}})
    app.instance("db", db)
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=True))
    app.instance("queue", manager)
    set_application(app)
    QueuedJob.set_connection(db)
    FailedJob.set_connection(db)
    JobBatch.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))
    await db.execute(sa.schema.CreateTable(FailedJob.__table__))
    await db.execute(sa.schema.CreateTable(JobBatch.__table__))
    return manager, db


async def test_batch_member_chain_head_and_unique_settle_together_on_postgres(
    postgres_url: str,
) -> None:
    """Success path: one job in a batch, heading a chain, and unique — the chain continues, the
    batch settles green, and the unique lock is released (a re-dispatch runs again)."""
    _COMBO_RUN.clear()
    _COMBO_THEN.clear()
    _COMBO_CATCH.clear()
    manager, db = await _combo_manager(postgres_url)
    try:
        head = ComboHeadOk("combo-ok")
        head.__arvel_chain__ = [serialize_instance(ComboTail("tail"))]
        batch = await (
            Bus.batch([head]).then(_combo_then).catch(_combo_catch).dispatch(manager=manager)
        )

        assert _COMBO_RUN == ["head-ok", "tail"]  # chain continued after the batch member ran
        assert await batch.finished()
        assert await batch.progress() == 100.0
        assert await batch.cancelled() is False
        assert _COMBO_THEN == [True] and _COMBO_CATCH == []

        # unique lock released → the same unique id dispatches + runs again
        await manager.push_instance(ComboHeadOk("combo-ok"))
        assert _COMBO_RUN.count("head-ok") == 2
    finally:
        for tbl in (JobBatch.__table__, FailedJob.__table__, QueuedJob.__table__):
            with contextlib.suppress(Exception):
                await db.execute(sa.schema.DropTable(tbl))
        await db.dispose()
        set_application(None)


async def test_batch_member_chain_head_unique_failure_cancels_chain_and_releases_lock_on_postgres(
    postgres_url: str,
) -> None:
    """Failure path: the head fails — the chain does NOT continue, the batch records the failure,
    the batch catch fires, and the unique lock is still released (no leaked lock)."""
    _COMBO_RUN.clear()
    _COMBO_THEN.clear()
    _COMBO_CATCH.clear()
    manager, db = await _combo_manager(postgres_url)
    try:
        head = ComboHeadBoom("combo-boom")
        head.__arvel_chain__ = [serialize_instance(ComboTail("tail"))]
        batch = await (
            Bus.batch([head]).then(_combo_then).catch(_combo_catch).dispatch(manager=manager)
        )

        assert "tail" not in _COMBO_RUN  # chain stopped at the failed head
        assert await batch.cancelled() is True
        assert _COMBO_CATCH == [True] and _COMBO_THEN == []

        # lock released on failure too → the same unique id runs again (would fail again, but runs)
        await manager.push_instance(ComboHeadBoom("combo-boom"))
        assert _COMBO_RUN.count("head-boom") == 2
    finally:
        for tbl in (JobBatch.__table__, FailedJob.__table__, QueuedJob.__table__):
            with contextlib.suppress(Exception):
                await db.execute(sa.schema.DropTable(tbl))
        await db.dispose()
        set_application(None)
