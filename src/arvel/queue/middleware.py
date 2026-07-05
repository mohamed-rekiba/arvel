"""arvel.queue.middleware — unique jobs (`ShouldBeUnique`) + job middleware (Laravel parity).

Job middleware wraps a job's `handle()` the same way HTTP middleware wraps a request: each pipe
decides whether/when to call `next_`. It's the exact `arvel.support.pipeline.Pipeline` onion shape
(`(value, next)`), reused as-is — no new pipeline machinery. `Job.middleware()` returns the list;
the worker (`QueueManager._invoke`) runs `handle()` through it.

A middleware that wants the job **not** to run right now (a lock already held, a rate limit hit)
raises :class:`JobShouldBeReleased` — a `BaseException`, not `Exception`, so it passes straight
through `run_job_with_retries`'s `except Exception` (a release is not a failed attempt; it must
never count against `tries`) up to `QueueManager._invoke`, which re-enqueues the job after the
given delay instead of running it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class JobShouldBeReleased(BaseException):
    """Raised by a job middleware to put the job back on the queue after ``delay`` seconds
    instead of running it now (Laravel ``$job->release($delay)``). Deliberately a
    ``BaseException`` (see module docstring) — never treated as a failed attempt."""

    def __init__(self, delay: float = 0) -> None:
        super().__init__(f"job released for {delay}s")
        self.delay = delay


class ShouldBeUnique:
    """Marker mixin: at most one instance of this job — keyed by its class + :meth:`unique_id`
    — may be queued/running at a time (Laravel ``ShouldBeUnique``). ``QueueManager.push``/
    ``push_instance`` acquire a :class:`~arvel.cache.CacheLock` before dispatch and silently skip
    (return ``None``) a second dispatch while it's held; the worker releases it once the job
    finishes processing, or ``unique_for`` seconds expire — whichever comes first."""

    #: The lock's TTL (seconds) — the safety net if the worker never gets to release it (a crash).
    unique_for: int = 3600

    def unique_id(self) -> str:
        """The key segment scoping *this* job's uniqueness slot. Empty by default (every instance
        of the class shares one "at most one at a time" slot) — override for per-argument
        uniqueness, e.g. ``return str(self.order_id)``."""
        return ""


def unique_lock_for(job: Any) -> Any:
    """The :class:`~arvel.cache.CacheLock` guarding ``job``'s uniqueness slot (its class +
    :meth:`ShouldBeUnique.unique_id`), TTL'd to ``job.unique_for``."""
    from arvel.queue import _qualified_name  # pyright: ignore[reportPrivateUsage]
    from arvel.support import cache

    name = f"unique_job:{_qualified_name(type(job))}:{job.unique_id()}"
    return cache().lock(name, seconds=getattr(job, "unique_for", 3600))


class WithoutOverlapping:
    """Serializes concurrent runs sharing ``key`` (Laravel job middleware ``WithoutOverlapping``):
    a :class:`~arvel.cache.CacheLock` guards ``key``; a run that finds it already held releases the
    job back onto the queue (after ``release_after`` seconds) instead of running now. ``expire`` is
    the lock's own TTL — the safety net if a holder dies mid-run without releasing."""

    def __init__(self, key: str, expire: int = 60, release_after: int = 0) -> None:
        self.key = key
        self.expire = expire
        self.release_after = release_after

    async def handle(self, job: Any, next_: Callable[[Any], Awaitable[Any]]) -> Any:
        from arvel.support import cache

        lock = cache().lock(f"job_overlap:{self.key}", seconds=self.expire)
        if not await lock.acquire():
            raise JobShouldBeReleased(self.release_after)
        try:
            return await next_(job)
        finally:
            await lock.release()


class RateLimited:
    """Caps executions of jobs sharing ``key`` to ``max_attempts`` per ``decay_seconds`` (Laravel
    job middleware ``RateLimited``) — over the limit, the job is released back onto the queue
    instead of running. ``limiter`` is duck-typed against
    :class:`arvel.http.rate_limiter.RateLimiter`'s counting verbs (``too_many_attempts``/``hit``/
    ``available_in``) rather than imported directly, so this stays a queue→http-free edge."""

    def __init__(self, limiter: Any, key: str, max_attempts: int, decay_seconds: int = 60) -> None:
        self._limiter = limiter
        self.key = key
        self.max_attempts = max_attempts
        self.decay_seconds = decay_seconds

    async def handle(self, job: Any, next_: Callable[[Any], Awaitable[Any]]) -> Any:
        if await self._limiter.too_many_attempts(self.key, self.max_attempts):
            wait = await self._limiter.available_in(self.key)
            raise JobShouldBeReleased(wait or self.decay_seconds)
        await self._limiter.hit(self.key, self.decay_seconds)
        return await next_(job)


class ThrottlesExceptions:
    """A simple circuit breaker (Laravel job middleware ``ThrottlesExceptions``): once
    ``max_exceptions`` failures land within ``decay_seconds``, further attempts release the job
    back onto the queue immediately instead of calling ``handle()`` (and failing again) — built
    entirely on the cache's existing counter verbs, no new plumbing."""

    def __init__(
        self, max_exceptions: int, decay_seconds: int = 60, *, key: str | None = None
    ) -> None:
        self.max_exceptions = max_exceptions
        self.decay_seconds = decay_seconds
        self._key = key

    def _cache_key(self, job: Any) -> str:
        if self._key is not None:
            return self._key
        from arvel.queue import _qualified_name  # pyright: ignore[reportPrivateUsage]

        return f"throttle_exceptions:{_qualified_name(type(job))}"

    async def handle(self, job: Any, next_: Callable[[Any], Awaitable[Any]]) -> Any:
        from arvel.support import cache

        repo = cache()
        key = self._cache_key(job)
        if int(await repo.get(key, 0)) >= self.max_exceptions:
            raise JobShouldBeReleased(self.decay_seconds)
        try:
            return await next_(job)
        except Exception:
            count = await repo.increment(key)
            if count == 1:
                await repo.expire(key, self.decay_seconds)
            raise


__all__ = [
    "JobShouldBeReleased",
    "RateLimited",
    "ShouldBeUnique",
    "ThrottlesExceptions",
    "WithoutOverlapping",
    "unique_lock_for",
]
