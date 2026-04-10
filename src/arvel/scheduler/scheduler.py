"""Scheduler — registers entries and evaluates/dispatches due jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from arvel.scheduler.entry import ScheduleEntry

if TYPE_CHECKING:
    from arvel.queue.contracts import QueueContract
    from arvel.queue.job import Job
    from arvel.scheduler.locks import LockBackend


class Scheduler:
    """Core scheduler that manages schedule entries and dispatches due jobs.

    Create entries via ``scheduler.job(MyJob).daily_at("08:00")``.
    Evaluate with ``await scheduler.run()`` to dispatch due jobs through the queue.
    """

    def __init__(
        self,
        queue: QueueContract,
        lock_backend: LockBackend | None = None,
    ) -> None:
        self._queue = queue
        self._lock_backend = lock_backend
        self._entries: list[ScheduleEntry] = []

    def job(self, job_class: type[Job]) -> ScheduleEntry:
        """Register a new scheduled job and return the entry for fluent configuration."""
        entry = ScheduleEntry(job_class=job_class)
        self._entries.append(entry)
        return entry

    def entries(self) -> list[ScheduleEntry]:
        """Return all registered schedule entries."""
        return list(self._entries)

    async def run(self, now: datetime | None = None) -> int:
        """Evaluate all entries and dispatch due jobs. Returns count dispatched."""
        if now is None:
            now = datetime.now(UTC)

        dispatched = 0
        for entry in self._entries:
            if not entry.is_due(now):
                continue
            if not entry.should_run():
                continue
            if entry.prevent_overlap and self._lock_backend is not None:
                lock_key = self._lock_key(entry)
                acquired = await self._lock_backend.acquire(lock_key, entry.overlap_expires_after)
                if not acquired:
                    continue

            job_instance = entry.job_class()
            await self._queue.dispatch(job_instance)
            dispatched += 1

        return dispatched

    @staticmethod
    def _lock_key(entry: ScheduleEntry) -> str:
        cls = entry.job_class
        return f"scheduler:overlap:{cls.__module__}.{cls.__qualname__}"
