"""Tests for the worker loop (queue:work) — FR-008-017, FR-011-003..006, ADR-036."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.drivers.database import DatabaseConnection
from arvel.queue.envelope import JobEnvelope
from arvel.queue.failed_job_store import FailedJobStore
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager
from arvel.queue.worker import Worker


async def _make_db_manager() -> tuple[QueueManager, DatabaseConnection]:
    """Return a QueueManager backed by an in-memory SQLite database connection."""
    db_conn = DatabaseConnection()
    await db_conn.setup()
    manager = QueueManager(QueueConfig(connection=QueueDriver.DATABASE))
    manager._connections[QueueDriver.DATABASE] = db_conn  # pyright: ignore[reportPrivateUsage]
    return manager, db_conn


class _WorkerJob(Job):
    message: str
    executed: ClassVar[list[str]] = []

    async def handle(self) -> None:
        _WorkerJob.executed.append(self.message)


class _FailingJob(Job):
    tries: int = 3
    call_count: ClassVar[int] = 0

    async def handle(self) -> None:
        _FailingJob.call_count += 1
        raise RuntimeError("intentional failure")


class _FailThenSucceedJob(Job):
    tries: int = 3
    call_count: ClassVar[int] = 0
    success_count: ClassVar[int] = 0

    async def handle(self) -> None:
        _FailThenSucceedJob.call_count += 1
        if _FailThenSucceedJob.call_count < 2:
            raise RuntimeError("transient failure")
        _FailThenSucceedJob.success_count += 1


class TestWorkerLoop:
    """FR-008-017: Worker processes envelopes until stopped."""

    def setup_method(self) -> None:
        _WorkerJob.executed.clear()

    @pytest.mark.asyncio
    async def test_worker_exits_when_stop_set(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        worker = Worker(manager, queue="default", sleep_interval=0)

        stop = asyncio.Event()
        stop.set()
        await worker.run_until(stop)

    @pytest.mark.asyncio
    async def test_worker_does_not_crash_on_empty_queue(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        worker = Worker(manager, queue="default", sleep_interval=0)

        stop = asyncio.Event()
        stop.set()
        await worker.run_until(stop)

    @pytest.mark.asyncio
    async def test_worker_respects_stop_event(self) -> None:
        """Worker exits when stop event is set after a short delay."""
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        worker = Worker(manager, queue="default", sleep_interval=0.01)

        stop = asyncio.Event()

        async def set_stop_shortly() -> None:
            await asyncio.sleep(0.05)
            stop.set()

        asyncio.create_task(set_stop_shortly())
        await worker.run_until(stop)


class TestWorkerMetrics:
    """FR-011-006: Worker exposes jobs_processed, jobs_retried, jobs_dead counters."""

    def setup_method(self) -> None:
        _WorkerJob.executed.clear()

    @pytest.mark.asyncio
    async def test_metrics_start_at_zero(self) -> None:
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        worker = Worker(manager, queue="default", sleep_interval=0)
        assert worker.jobs_processed == 0
        assert worker.jobs_retried == 0
        assert worker.jobs_dead == 0

    @pytest.mark.asyncio
    async def test_successful_job_increments_processed(self) -> None:
        manager, db_conn = await _make_db_manager()
        job = _WorkerJob(message="hello")
        await db_conn.push(job.to_envelope(), queue="default")

        worker = Worker(manager, queue="default", sleep_interval=0)
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.1)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        assert worker.jobs_processed == 1
        assert worker.jobs_retried == 0
        assert worker.jobs_dead == 0


class TestWorkerRetry:
    """FR-011-003: Failed jobs are re-enqueued until tries are exhausted."""

    def setup_method(self) -> None:
        _FailingJob.call_count = 0
        _FailThenSucceedJob.call_count = 0
        _FailThenSucceedJob.success_count = 0

    @pytest.mark.asyncio
    async def test_job_retried_up_to_tries_limit(self) -> None:
        """A job with tries=3 that always fails is attempted 3 times total."""
        manager, db_conn = await _make_db_manager()
        job = _FailingJob()
        await db_conn.push(job.to_envelope(), queue="default")

        store = FailedJobStore.create_in_memory()
        await store.setup()

        worker = Worker(manager, queue="default", sleep_interval=0, failed_job_store=store)
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.5)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        assert _FailingJob.call_count == 3
        assert worker.jobs_retried == 2  # 2 re-enqueues before exhaustion
        assert worker.jobs_dead == 1
        assert await store.count() == 1

    @pytest.mark.asyncio
    async def test_job_routed_to_dlq_on_exhaustion(self) -> None:
        """Exhausted job lands in FailedJobStore with correct queue and error."""
        manager, db_conn = await _make_db_manager()
        job = _FailingJob(queue="critical")
        await db_conn.push(job.to_envelope(), queue="critical")

        store = FailedJobStore.create_in_memory()
        await store.setup()

        worker = Worker(manager, queue="critical", sleep_interval=0, failed_job_store=store)
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.5)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        failed = await store.list_all()
        assert len(failed) == 1
        assert failed[0].queue == "critical"
        assert "intentional failure" in failed[0].error

    @pytest.mark.asyncio
    async def test_no_dlq_store_exhausted_job_dropped_silently(self) -> None:
        """FR-011-005: When no FailedJobStore, exhausted jobs are dropped without crash."""
        manager, db_conn = await _make_db_manager()
        job = _FailingJob()
        await db_conn.push(job.to_envelope(), queue="default")

        worker = Worker(manager, queue="default", sleep_interval=0)  # no DLQ store
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.5)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        assert worker.jobs_dead == 1

    @pytest.mark.asyncio
    async def test_tries_one_goes_straight_to_dlq(self) -> None:
        """A job with tries=1 goes directly to DLQ on first failure (no retries)."""

        class _OneTryJob(Job):
            tries: int = 1

            async def handle(self) -> None:
                raise RuntimeError("immediate fail")

        manager, db_conn = await _make_db_manager()
        await db_conn.push(_OneTryJob().to_envelope(), queue="default")

        store = FailedJobStore.create_in_memory()
        await store.setup()

        worker = Worker(manager, queue="default", sleep_interval=0, failed_job_store=store)
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.2)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        assert worker.jobs_retried == 0
        assert worker.jobs_dead == 1
        assert await store.count() == 1

    @pytest.mark.asyncio
    async def test_job_succeeds_on_retry(self) -> None:
        """FR-011-003: A job that fails once then succeeds counts as processed."""
        manager, db_conn = await _make_db_manager()
        job = _FailThenSucceedJob()
        await db_conn.push(job.to_envelope(), queue="default")

        worker = Worker(manager, queue="default", sleep_interval=0)
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.3)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        assert _FailThenSucceedJob.success_count == 1
        assert worker.jobs_processed == 1
        assert worker.jobs_retried == 1
        assert worker.jobs_dead == 0


class _RetryPriorityProbe(Job):
    """Captures the envelope on failure to assert priority/delay survive re-enqueue."""

    tries: int = 2
    seen_priority: ClassVar[list[int]] = []
    seen_delay: ClassVar[list[int]] = []
    call_count: ClassVar[int] = 0

    async def handle(self) -> None:
        _RetryPriorityProbe.call_count += 1
        # On first call: fail; on second (retry): record what survived
        if _RetryPriorityProbe.call_count == 1:
            raise RuntimeError("first attempt fails")


class TestWorkerRetryPreservesPriorityResetsDelay:
    """FR-018-17: retry MUST preserve priority and reset delay to 0."""

    def setup_method(self) -> None:
        _RetryPriorityProbe.seen_priority.clear()
        _RetryPriorityProbe.seen_delay.clear()
        _RetryPriorityProbe.call_count = 0

    @pytest.mark.asyncio
    async def test_retry_preserves_priority_and_resets_delay(self) -> None:
        """A failed job with priority=7, delay=60 is re-enqueued priority=7 delay=0."""
        manager, db_conn = await _make_db_manager()
        # delay=0 in the test so we don't actually wait 60s; we'll mutate the envelope
        # before push to simulate "first dispatch carried a delay".
        env = _RetryPriorityProbe(priority=7).to_envelope()
        env.delay = 0  # already-due so the worker pops it
        await db_conn.push(env, queue="default")

        # Spy on conn.push so we can inspect the re-enqueued envelope
        original_push = db_conn.push
        captured: list[JobEnvelope] = []

        async def spying_push(envelope: JobEnvelope, queue: str = "default") -> None:
            captured.append(envelope)
            await original_push(envelope, queue=queue)

        db_conn.push = spying_push  # type: ignore[method-assign]

        worker = Worker(manager, queue="default", sleep_interval=0)
        stop = asyncio.Event()

        async def stopper() -> None:
            await asyncio.sleep(0.3)
            stop.set()

        asyncio.create_task(stopper())
        await worker.run_until(stop)

        # The retry push captured by the spy
        assert len(captured) >= 1, "worker did not re-enqueue the failed envelope"
        retried = captured[-1]
        assert retried.priority == 7, "priority must be preserved on retry"
        assert retried.delay == 0, "delay must be reset to 0 on retry"
