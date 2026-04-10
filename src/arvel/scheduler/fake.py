"""SchedulerFake — test double for asserting schedule configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from arvel.scheduler.entry import ScheduleEntry

if TYPE_CHECKING:
    from arvel.queue.job import Job


class SchedulerFake:
    """Captures scheduled entries for test assertions without dispatching to a real queue."""

    def __init__(self) -> None:
        self._entries: list[ScheduleEntry] = []
        self.dispatched_jobs: list[Job] = []

    def job(self, job_class: type[Job]) -> ScheduleEntry:
        """Register a scheduled job (captured, not dispatched)."""
        entry = ScheduleEntry(job_class=job_class)
        self._entries.append(entry)
        return entry

    def entries(self) -> list[ScheduleEntry]:
        """Return all registered entries."""
        return list(self._entries)

    def assert_scheduled(self, job_class: type[Job]) -> None:
        """Assert that a job class has been registered."""
        for entry in self._entries:
            if entry.job_class is job_class:
                return
        raise AssertionError(
            f"{job_class.__name__} is not scheduled. "
            f"Registered: {[e.job_class.__name__ for e in self._entries]}"
        )

    def assert_not_scheduled(self, job_class: type[Job]) -> None:
        """Assert that a job class has NOT been registered."""
        for entry in self._entries:
            if entry.job_class is job_class:
                raise AssertionError(f"{job_class.__name__} is scheduled but should not be")

    def due_at(self, dt: datetime) -> list[ScheduleEntry]:
        """Return entries that would be due at the given datetime."""
        return [entry for entry in self._entries if entry.is_due(dt)]

    async def run(self, now: datetime | None = None) -> int:
        """Simulate evaluation — capture dispatched jobs instead of queuing them."""
        if now is None:
            now = datetime.now(UTC)

        count = 0
        for entry in self._entries:
            if entry.is_due(now) and entry.should_run():
                self.dispatched_jobs.append(entry.job_class())
                count += 1
        return count
