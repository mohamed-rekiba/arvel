"""Tests for Scheduler — registry, evaluation, queue dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from arvel.queue.contracts import QueueContract
from arvel.queue.job import Job
from arvel.scheduler.scheduler import Scheduler


class _JobA(Job):
    async def handle(self) -> None:
        pass


class _JobB(Job):
    async def handle(self) -> None:
        pass


class _JobC(Job):
    async def handle(self) -> None:
        pass


@pytest.fixture
def mock_queue() -> AsyncMock:
    return AsyncMock(spec=QueueContract)


@pytest.fixture
def scheduler(mock_queue: AsyncMock) -> Scheduler:
    return Scheduler(queue=mock_queue)


class TestSchedulerRegistration:
    """FR-001: Register entries via fluent API."""

    def test_register_single_entry(self, scheduler: Scheduler) -> None:
        scheduler.job(_JobA).daily()
        assert len(scheduler.entries()) == 1

    def test_register_multiple_entries(self, scheduler: Scheduler) -> None:
        scheduler.job(_JobA).daily()
        scheduler.job(_JobB).hourly()
        assert len(scheduler.entries()) == 2

    def test_entry_stores_job_class(self, scheduler: Scheduler) -> None:
        scheduler.job(_JobA).daily()
        entry = scheduler.entries()[0]
        assert entry.job_class is _JobA

    def test_job_returns_schedule_entry(self, scheduler: Scheduler) -> None:
        from arvel.scheduler.entry import ScheduleEntry

        entry = scheduler.job(_JobA)
        assert isinstance(entry, ScheduleEntry)


class TestSchedulerRun:
    """FR-004 + FR-005: Evaluate entries and dispatch due jobs via QueueContract."""

    async def test_dispatches_due_job(self, scheduler: Scheduler, mock_queue: AsyncMock) -> None:
        scheduler.job(_JobA).every_minute()
        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        count = await scheduler.run(now)
        assert count == 1
        mock_queue.dispatch.assert_called_once()

    async def test_skips_not_due_job(self, scheduler: Scheduler, mock_queue: AsyncMock) -> None:
        scheduler.job(_JobA).daily_at("08:00")
        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        count = await scheduler.run(now)
        assert count == 0
        mock_queue.dispatch.assert_not_called()

    async def test_dispatches_only_due_jobs(
        self, scheduler: Scheduler, mock_queue: AsyncMock
    ) -> None:
        scheduler.job(_JobA).every_minute()
        scheduler.job(_JobB).daily_at("08:00")
        scheduler.job(_JobC).hourly()
        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        count = await scheduler.run(now)
        assert count == 2
        assert mock_queue.dispatch.call_count == 2

    async def test_dispatched_job_is_instance_of_job_class(
        self, scheduler: Scheduler, mock_queue: AsyncMock
    ) -> None:
        scheduler.job(_JobA).every_minute()
        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        await scheduler.run(now)
        dispatched_job = mock_queue.dispatch.call_args[0][0]
        assert isinstance(dispatched_job, _JobA)

    async def test_respects_when_condition(
        self, scheduler: Scheduler, mock_queue: AsyncMock
    ) -> None:
        scheduler.job(_JobA).every_minute().when(lambda: False)
        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        count = await scheduler.run(now)
        assert count == 0

    async def test_respects_skip_condition(
        self, scheduler: Scheduler, mock_queue: AsyncMock
    ) -> None:
        scheduler.job(_JobA).every_minute().skip(lambda: True)
        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        count = await scheduler.run(now)
        assert count == 0

    async def test_run_returns_zero_when_no_entries(self, scheduler: Scheduler) -> None:
        count = await scheduler.run()
        assert count == 0

    async def test_run_uses_current_time_by_default(
        self, scheduler: Scheduler, mock_queue: AsyncMock
    ) -> None:
        scheduler.job(_JobA).every_minute()
        count = await scheduler.run()
        assert count == 1
