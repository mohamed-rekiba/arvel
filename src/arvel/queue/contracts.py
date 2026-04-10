"""Queue contract — ABC for swappable queue drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta

    from arvel.queue.job import Job


class QueueContract(ABC):
    """Abstract base class for queue drivers.

    Implementations: SyncQueue (testing), NullQueue (dry-run),
    TaskiqQueue (multi-broker via Taskiq).
    """

    @abstractmethod
    async def dispatch(self, job: Job) -> None:
        """Enqueue a job for immediate processing."""

    @abstractmethod
    async def later(self, delay: timedelta, job: Job) -> None:
        """Enqueue a job for processing after a delay."""

    @abstractmethod
    async def bulk(self, jobs: Sequence[Job]) -> None:
        """Enqueue multiple jobs at once."""

    @abstractmethod
    async def size(self, queue_name: str = "default") -> int:
        """Return the number of pending jobs in the given queue."""
