"""Tests for the database driver
Uses in-memory SQLite via arvel's test infrastructure.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from arvel.queue.config import DatabaseQueueConfig
from arvel.queue.drivers.database import DatabaseConnection
from arvel.queue.envelope import JobEnvelope
from arvel.queue.job import Job


class _DbJob(Job):
    message: str

    async def handle(self) -> None:
        pass


@pytest_asyncio.fixture
async def db_driver() -> DatabaseConnection:
    config = DatabaseQueueConfig()
    driver = DatabaseConnection(config)
    await driver.setup()
    return driver


class TestDatabaseDriver:
    """Database driver persists jobs in the jobs table."""

    @pytest.mark.asyncio
    async def test_push_increases_size(self, db_driver: DatabaseConnection) -> None:
        job = _DbJob(message="db-job")
        await db_driver.push(job.to_envelope(), queue="default")
        assert await db_driver.size(queue="default") == 1

    @pytest.mark.asyncio
    async def test_pop_returns_pushed_envelope(self, db_driver: DatabaseConnection) -> None:
        job = _DbJob(message="pop-me")
        await db_driver.push(job.to_envelope(), queue="default")
        envelope = await db_driver.pop_blocking(queue="default", timeout=0)
        assert envelope is not None
        assert envelope.payload["message"] == "pop-me"

    @pytest.mark.asyncio
    async def test_pop_reserves_then_delete_reserved_removes_row(
        self, db_driver: DatabaseConnection
    ) -> None:
        """Pop reserves the row (still counted in size); delete_reserved removes it."""
        job = _DbJob(message="retried")
        await db_driver.push(job.to_envelope(), queue="default")
        envelope = await db_driver.pop_blocking(queue="default", timeout=0)
        assert envelope is not None
        assert envelope.receipt is not None
        # Reserved, not deleted — still present until the worker acks it.
        assert await db_driver.size(queue="default") == 1
        # A second pop won't hand out the in-flight row.
        assert await db_driver.pop_blocking(queue="default", timeout=0) is None
        await db_driver.delete_reserved(envelope)
        assert await db_driver.size(queue="default") == 0

    @pytest.mark.asyncio
    async def test_reservation_lapses_after_retry_after(
        self, db_driver: DatabaseConnection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reserved row a crashed worker never acked is reclaimable after retry_after."""
        clock = {"now": 1_000_000.0}
        monkeypatch.setattr("arvel.queue.drivers.database.time.time", lambda: clock["now"])

        await db_driver.push(_DbJob(message="orphan").to_envelope(), queue="default")
        first = await db_driver.pop_blocking(queue="default", timeout=0)
        assert first is not None
        # Worker "crashes" — no delete_reserved. Still reserved, not yet reclaimable.
        assert await db_driver.pop_blocking(queue="default", timeout=0) is None
        # Advance past the visibility timeout (default 90s).
        clock["now"] += 91
        redelivered = await db_driver.pop_blocking(queue="default", timeout=0)
        assert redelivered is not None
        assert redelivered.payload["message"] == "orphan"

    @pytest.mark.asyncio
    async def test_pop_empty_queue_returns_none(self, db_driver: DatabaseConnection) -> None:
        result = await db_driver.pop_blocking(queue="empty", timeout=0)
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_empties_queue(self, db_driver: DatabaseConnection) -> None:
        for i in range(3):
            job = _DbJob(message=f"job-{i}")
            await db_driver.push(job.to_envelope(), queue="default")
        await db_driver.clear(queue="default")
        assert await db_driver.size(queue="default") == 0

    @pytest.mark.asyncio
    async def test_delayed_job_not_returned_immediately(
        self, db_driver: DatabaseConnection
    ) -> None:
        """Jobs whose envelope.delay > 0 are not popped before available_at."""
        job = _DbJob(message="delayed", delay=3600)
        await db_driver.push(job.to_envelope(), queue="default")
        result = await db_driver.pop_blocking(queue="default", timeout=0)
        assert result is None

    @pytest.mark.asyncio
    async def test_pop_orders_by_priority_then_available_at(
        self, db_driver: DatabaseConnection
    ) -> None:
        """pop SELECT applies ORDER BY priority DESC, available_at ASC."""
        # Push lower priority first (would be FIFO under the old query)
        await db_driver.push(_DbJob(message="low").to_envelope(), queue="default")
        # Then push higher priority — should pop FIRST
        await db_driver.push(_DbJob(message="high", priority=7).to_envelope(), queue="default")
        first = await db_driver.pop_blocking(queue="default", timeout=0)
        assert first is not None
        assert first.payload["message"] == "high"
        second = await db_driver.pop_blocking(queue="default", timeout=0)
        assert second is not None
        assert second.payload["message"] == "low"

    @pytest.mark.asyncio
    async def test_unknown_job_class_goes_to_failed(self, db_driver: DatabaseConnection) -> None:
        """Deserialization of unknown class writes a FailedJob row."""
        env = JobEnvelope(job_class="ghost.GhostJob", payload={})
        await db_driver.push(env, queue="default")
        from arvel.queue.failed_job_store import FailedJobStore

        store = FailedJobStore(db_driver.session_factory)
        store.set_engine(db_driver.engine)
        await store.setup()
        await db_driver.pop_blocking(queue="default", timeout=0)
        count = await store.count()
        assert count >= 1
