"""Chain — sequential job execution primitive."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.queue.contracts import QueueContract
    from arvel.queue.job import Job


class Chain:
    """Dispatches jobs in sequence, halting on permanent failure.

    Each job runs after the previous one succeeds. If any job fails
    (after exhausting retries), the chain stops and the error propagates.
    """

    def __init__(self, *jobs: Job) -> None:
        self.jobs = list(jobs)

    async def dispatch(self, queue: QueueContract) -> None:
        """Execute all jobs in order via the given queue driver."""
        for job in self.jobs:
            await queue.dispatch(job)
