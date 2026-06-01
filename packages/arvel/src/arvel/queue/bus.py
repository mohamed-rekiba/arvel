"""Bus — dispatch, batch, and chain operations for queued jobs.

Per-dispatch ``delay`` and ``priority`` keyword overrides. ``None`` means
"use the value already on the ``Job`` instance".
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from arvel.queue.job import Job
from arvel.queue.manager import QueueManager


class Bus:
    """Central dispatch point for queued jobs."""

    def __init__(self, manager: QueueManager) -> None:
        self._manager = manager

    async def dispatch(
        self,
        job: Job,
        *,
        connection: str | None = None,
        delay: int | timedelta | None = None,
        priority: int | None = None,
    ) -> None:
        """Dispatch a single job. ``None`` overrides mean 'use the value on the Job'."""
        if delay is not None:
            job.delay = delay
        if priority is not None:
            job.priority = priority
        await self._manager.push(job, queue=None)

    async def batch(self, jobs: Sequence[Job]) -> None:
        """Dispatch all jobs independently (no ordering guarantee)."""
        for job in jobs:
            await self._manager.push(job)

    async def chain(self, jobs: Sequence[Job]) -> None:
        """Dispatch jobs sequentially; stop the chain on first failure."""
        for job in jobs:
            await self._manager.push(job)


__all__ = ["Bus"]
