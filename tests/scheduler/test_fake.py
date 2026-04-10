"""Tests for SchedulerFake — test assertions and simulated evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arvel.queue.job import Job
from arvel.scheduler.fake import SchedulerFake


class _ReportJob(Job):
    async def handle(self) -> None:
        pass


class _CleanupJob(Job):
    async def handle(self) -> None:
        pass


class _UnscheduledJob(Job):
    async def handle(self) -> None:
        pass


class TestSchedulerFakeRegistration:
    """FR-012: SchedulerFake captures registered entries."""

    def test_captures_entry(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).daily()
        assert len(fake.entries()) == 1

    def test_assert_scheduled_passes(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).daily()
        fake.assert_scheduled(_ReportJob)

    def test_assert_scheduled_fails(self) -> None:
        fake = SchedulerFake()
        with pytest.raises(AssertionError):
            fake.assert_scheduled(_ReportJob)

    def test_assert_not_scheduled_passes(self) -> None:
        fake = SchedulerFake()
        fake.assert_not_scheduled(_UnscheduledJob)

    def test_assert_not_scheduled_fails(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).daily()
        with pytest.raises(AssertionError):
            fake.assert_not_scheduled(_ReportJob)


class TestSchedulerFakeDueAt:
    """FR-012: due_at simulates time evaluation."""

    def test_due_at_returns_matching_entries(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).daily_at("08:00")
        fake.job(_CleanupJob).daily_at("23:00")

        at_8am = datetime(2026, 4, 6, 8, 0, 0, tzinfo=UTC)
        due = fake.due_at(at_8am)
        assert len(due) == 1
        assert due[0].job_class is _ReportJob

    def test_due_at_returns_empty_when_nothing_due(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).daily_at("08:00")

        at_noon = datetime(2026, 4, 6, 12, 0, 0, tzinfo=UTC)
        due = fake.due_at(at_noon)
        assert len(due) == 0


class TestSchedulerFakeDispatchedJobs:
    """FR-012: dispatched_jobs tracks what would have been dispatched."""

    async def test_dispatched_jobs_populated_after_run(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).every_minute()

        now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        await fake.run(now)
        assert len(fake.dispatched_jobs) == 1
        assert isinstance(fake.dispatched_jobs[0], _ReportJob)

    async def test_dispatched_jobs_empty_before_run(self) -> None:
        fake = SchedulerFake()
        fake.job(_ReportJob).every_minute()
        assert len(fake.dispatched_jobs) == 0
