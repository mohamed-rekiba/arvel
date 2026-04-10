"""SyncQueue — executes jobs immediately in-process (for testing/dev)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.queue.contracts import QueueContract

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta

    from arvel.queue.job import Job


class SyncQueue(QueueContract):
    """Executes jobs synchronously in the current process.

    Useful for testing and local development where you don't
    need a real queue backend. Uses ``JobRunner`` for retry/timeout
    parity with production drivers.
    """

    async def dispatch(self, job: Job) -> None:
        from arvel.queue.worker import JobRunner

        runner = JobRunner()
        await runner.execute(job)

    async def later(self, delay: timedelta, job: Job) -> None:
        from arvel.queue.worker import JobRunner

        runner = JobRunner()
        await runner.execute(job)

    async def bulk(self, jobs: Sequence[Job]) -> None:
        from arvel.queue.worker import JobRunner

        runner = JobRunner()
        for job in jobs:
            await runner.execute(job)

    async def size(self, queue_name: str = "default") -> int:
        return 0
