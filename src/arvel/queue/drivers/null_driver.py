"""NullQueue — silently discards all jobs (for dry-run/testing)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.queue.contracts import QueueContract

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta

    from arvel.queue.job import Job


class NullQueue(QueueContract):
    """Discards all dispatched jobs without executing them.

    Useful for testing scenarios where you want to verify
    dispatch calls without any side effects.
    """

    async def dispatch(self, job: Job) -> None:
        pass

    async def later(self, delay: timedelta, job: Job) -> None:
        pass

    async def bulk(self, jobs: Sequence[Job]) -> None:
        pass

    async def size(self, queue_name: str = "default") -> int:
        return 0
