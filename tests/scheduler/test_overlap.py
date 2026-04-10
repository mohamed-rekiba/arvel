"""Tests for overlap prevention integration with Scheduler."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from arvel.queue.contracts import QueueContract
from arvel.queue.job import Job
from arvel.scheduler.locks import InMemoryLockBackend
from arvel.scheduler.scheduler import Scheduler


class _SlowJob(Job):
    async def handle(self) -> None:
        pass


@pytest.fixture
def mock_queue() -> AsyncMock:
    return AsyncMock(spec=QueueContract)


class TestOverlapPrevention:
    """FR-009: without_overlapping prevents duplicate dispatch."""

    async def test_skips_when_lock_held(self, mock_queue: AsyncMock) -> None:
        lock = InMemoryLockBackend()
        scheduler = Scheduler(queue=mock_queue, lock_backend=lock)
        scheduler.job(_SlowJob).every_minute().without_overlapping()

        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        await scheduler.run(now)
        assert mock_queue.dispatch.call_count == 1

        count = await scheduler.run(now)
        assert count == 0
        assert mock_queue.dispatch.call_count == 1

    async def test_dispatches_after_lock_released(self, mock_queue: AsyncMock) -> None:
        lock = InMemoryLockBackend()
        scheduler = Scheduler(queue=mock_queue, lock_backend=lock)
        scheduler.job(_SlowJob).every_minute().without_overlapping()

        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        await scheduler.run(now)

        key = f"scheduler:overlap:{_SlowJob.__module__}.{_SlowJob.__qualname__}"
        await lock.release(key)

        count = await scheduler.run(now)
        assert count == 1

    async def test_no_overlap_prevention_dispatches_always(self, mock_queue: AsyncMock) -> None:
        lock = InMemoryLockBackend()
        scheduler = Scheduler(queue=mock_queue, lock_backend=lock)
        scheduler.job(_SlowJob).every_minute()

        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        await scheduler.run(now)
        await scheduler.run(now)
        assert mock_queue.dispatch.call_count == 2

    async def test_expired_lock_allows_dispatch(self, mock_queue: AsyncMock) -> None:
        lock = InMemoryLockBackend()
        scheduler = Scheduler(queue=mock_queue, lock_backend=lock)
        scheduler.job(_SlowJob).every_minute().without_overlapping(expires_after=0)

        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        await scheduler.run(now)
        count = await scheduler.run(now)
        assert count == 1
