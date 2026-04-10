"""Job middleware — wraps job execution with cross-cutting concerns.

Built-in middleware:
- ``RateLimited``: limit how many times a job key runs within a window
- ``WithoutOverlapping``: prevent concurrent execution of the same job key
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from arvel.lock.contracts import LockContract
    from arvel.queue.job import Job


class JobMiddleware:
    """Base class for job middleware.

    Subclass and implement ``handle()``. Call ``await next_call(job)``
    to continue the chain, or return without calling to skip execution.
    """

    async def handle(self, job: Job, next_call: Callable[[Job], Awaitable[None]]) -> None:
        await next_call(job)


class RateLimited(JobMiddleware):
    """Limits job execution to ``max_attempts`` within ``decay_seconds``.

    Uses a LockContract-based counter. When the limit is exceeded,
    the job is silently skipped (released back for later processing).
    """

    def __init__(
        self,
        *,
        key: str,
        max_attempts: int,
        decay_seconds: int,
        lock: LockContract,
    ) -> None:
        self._key = key
        self._max_attempts = max_attempts
        self._decay_seconds = decay_seconds
        self._lock = lock
        self._attempts: dict[str, list[float]] = {}

    def _rate_key(self) -> str:
        return f"rate-limit:{self._key}"

    async def handle(self, job: Job, next_call: Callable[[Job], Awaitable[None]]) -> None:
        now = time.monotonic()
        rate_key = self._rate_key()

        timestamps = self._attempts.get(rate_key, [])
        cutoff = now - self._decay_seconds
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self._max_attempts:
            return  # skip — rate limit exceeded

        timestamps.append(now)
        self._attempts[rate_key] = timestamps
        await next_call(job)


class WithoutOverlapping(JobMiddleware):
    """Prevents concurrent execution of jobs with the same key.

    Uses a distributed lock. If the lock is already held, the job
    is silently skipped (released for later processing).
    """

    def __init__(
        self,
        *,
        key: str,
        lock: LockContract,
        release_after: int = 300,
    ) -> None:
        self._key = key
        self._lock = lock
        self._release_after = release_after

    def _lock_key(self) -> str:
        return f"without-overlapping:{self._key}"

    async def handle(self, job: Job, next_call: Callable[[Job], Awaitable[None]]) -> None:
        lock_key = self._lock_key()
        acquired = await self._lock.acquire(lock_key, ttl=self._release_after)
        if not acquired:
            return  # skip — another instance is running

        try:
            await next_call(job)
        finally:
            await self._lock.release(lock_key)
