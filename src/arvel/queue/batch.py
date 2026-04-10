"""Batch — parallel job execution with completion callback."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from arvel.queue.contracts import QueueContract
    from arvel.queue.job import Job


class BatchResult:
    """Tracks batch execution results."""

    def __init__(self) -> None:
        self.succeeded: list[Job] = []
        self.failed: list[tuple[Job, Exception]] = []

    @property
    def has_failures(self) -> bool:
        return len(self.failed) > 0


class Batch:
    """Dispatches jobs concurrently and fires a callback when all complete.

    Unlike Chain, Batch doesn't stop on failure. It collects results
    and invokes the callback (if set) after all jobs finish.
    """

    def __init__(self, jobs: Sequence[Job]) -> None:
        self.jobs = list(jobs)
        self.callback: Job | None = None

    def then(self, callback: Job) -> Batch:
        """Set a job to run after all batch jobs complete."""
        self.callback = callback
        return self

    async def dispatch(self, queue: QueueContract) -> BatchResult:
        """Execute all jobs via the given queue driver and fire callback."""
        result = BatchResult()

        for job in self.jobs:
            try:
                await queue.dispatch(job)
                result.succeeded.append(job)
            except Exception as exc:
                result.failed.append((job, exc))

        if self.callback is not None:
            await queue.dispatch(self.callback)

        return result
