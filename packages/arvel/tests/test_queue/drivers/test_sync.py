"""Tests for the sync driver"""

from __future__ import annotations

from typing import ClassVar

import pytest
from arvel.queue.drivers.sync import SyncConnection
from arvel.queue.job import Job


class _SyncJob(Job):
    message: str
    executed: ClassVar[list[str]] = []

    async def handle(self) -> None:
        _SyncJob.executed.append(self.message)


class _FailingJob(Job):
    async def handle(self) -> None:
        raise RuntimeError("intentional failure")


class TestSyncDriver:
    """Sync driver executes inline."""

    def setup_method(self) -> None:
        _SyncJob.executed.clear()

    @pytest.mark.asyncio
    async def test_push_executes_job_immediately(self) -> None:
        driver = SyncConnection()
        job = _SyncJob(message="sync-exec")
        await driver.push(job.to_envelope(), queue="default")
        assert "sync-exec" in _SyncJob.executed

    @pytest.mark.asyncio
    async def test_push_failing_job_raises(self) -> None:
        driver = SyncConnection()
        job = _FailingJob()
        with pytest.raises(RuntimeError, match="intentional failure"):
            await driver.push(job.to_envelope(), queue="default")

    @pytest.mark.asyncio
    async def test_pop_blocking_returns_none(self) -> None:
        driver = SyncConnection()
        result = await driver.pop_blocking(queue="default", timeout=0)
        assert result is None

    @pytest.mark.asyncio
    async def test_size_is_always_zero(self) -> None:
        driver = SyncConnection()
        assert await driver.size(queue="default") == 0

    @pytest.mark.asyncio
    async def test_clear_is_noop(self) -> None:
        driver = SyncConnection()
        await driver.clear(queue="default")

    def test_unknown_job_class_not_in_registry(self) -> None:
        from arvel.queue.registry import JobRegistry

        assert "evil.module.EvilJob" not in JobRegistry


class TestSyncDriverDelay:
    """sync driver honours envelope.delay via asyncio.sleep."""

    def setup_method(self) -> None:
        _SyncJob.executed.clear()

    @pytest.mark.asyncio
    async def test_zero_delay_returns_immediately(self) -> None:
        import time

        driver = SyncConnection()
        job = _SyncJob(message="instant", delay=0)
        start = time.monotonic()
        await driver.push(job.to_envelope(), queue="default")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
        assert "instant" in _SyncJob.executed

    @pytest.mark.asyncio
    async def test_positive_delay_sleeps_then_handles(self) -> None:
        import time

        driver = SyncConnection()
        # 0.05 s is enough to be measurable without slowing the suite
        job = _SyncJob(message="delayed", delay=0)
        env = job.to_envelope()
        env.delay = 1  # bypass Pydantic int-second cap
        start = time.monotonic()
        # Override delay via direct envelope mutation — keeps the test under 2 s
        # (sync sleeps for exactly envelope.delay seconds; we want >=1 s observable)
        await driver.push(env, queue="default")
        elapsed = time.monotonic() - start
        assert elapsed >= 1.0
        assert "delayed" in _SyncJob.executed

    @pytest.mark.asyncio
    async def test_priority_is_noop_for_sync(self) -> None:
        """priority on sync driver is a documented no-op."""
        driver = SyncConnection()
        job_high = _SyncJob(message="h", priority=9)
        job_low = _SyncJob(message="l", priority=0)
        # Sync runs in calling order — priority does not reorder
        await driver.push(job_low.to_envelope(), queue="default")
        await driver.push(job_high.to_envelope(), queue="default")
        assert _SyncJob.executed == ["l", "h"]
