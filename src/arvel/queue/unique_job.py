"""Unique job guard — prevents duplicate dispatches within a time window.

Uses the LockContract to acquire a uniqueness lock keyed by a SHA-256
hash of the job's unique ID. Gracefully degrades when the lock backend
is unavailable.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.lock.contracts import LockContract
    from arvel.queue.job import Job

logger = Log.named("arvel.queue.unique_job")


class UniqueJobGuard:
    """Dispatch-time guard that prevents duplicate job execution.

    Args:
        lock: A LockContract implementation for distributed uniqueness.
    """

    def __init__(self, *, lock: LockContract) -> None:
        self._lock = lock

    def _make_key(self, job: Job) -> str:
        """Build a hashed lock key from the job's unique ID."""
        raw_id = job.get_unique_id()
        hashed = hashlib.sha256(raw_id.encode()).hexdigest()
        return f"unique-job:{hashed}"

    async def acquire(self, job: Job) -> bool:
        """Try to acquire the uniqueness lock.

        Returns True if the job should proceed (lock acquired or no
        uniqueness configured). Returns False if the job is a duplicate.
        """
        if not job.unique_for:
            return True

        key = self._make_key(job)
        try:
            acquired = await self._lock.acquire(key, ttl=job.unique_for)
            return acquired
        except Exception:
            logger.warning(
                "Uniqueness lock backend unavailable for %s — allowing dispatch",
                type(job).__name__,
            )
            return True

    async def release_for_processing(self, job: Job) -> None:
        """Release the uniqueness lock when ``unique_until_processing=True``.

        Called at the start of job processing so a new dispatch of the
        same job is allowed while this one runs.
        """
        if not job.unique_for or not job.unique_until_processing:
            return

        key = self._make_key(job)
        try:
            await self._lock.release(key)
        except Exception:
            logger.warning(
                "Failed to release uniqueness lock for %s — continuing",
                type(job).__name__,
            )
