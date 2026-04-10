"""Tests for job middleware — Story 2.

AC-010: RateLimited releases job when limit exceeded
AC-011: WithoutOverlapping releases job when key is locked
AC-012: Multiple middleware run in declared order
AC-013: Middleware that doesn't call next skips job without failure
"""

from __future__ import annotations

from arvel.lock.drivers.memory_driver import MemoryLock
from arvel.queue.job import Job
from arvel.queue.middleware import (
    JobMiddleware,
    RateLimited,
    WithoutOverlapping,
)
from arvel.queue.worker import JobRunner


class SimpleJob(Job):
    handled: bool = False

    async def handle(self) -> None:
        self.handled = True


class SkippingMiddleware(JobMiddleware):
    """Middleware that never calls next — skips the job."""

    async def handle(self, job, next_call) -> None:
        pass  # intentionally does not call next


class OrderTracker(JobMiddleware):
    """Records execution order."""

    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self.log = log

    async def handle(self, job, next_call) -> None:
        self.log.append(f"before-{self.name}")
        await next_call(job)
        self.log.append(f"after-{self.name}")


# ──── AC-010: RateLimited ────


class TestRateLimited:
    async def test_allows_job_under_limit(self) -> None:
        lock = MemoryLock()
        mw = RateLimited(key="api", max_attempts=10, decay_seconds=60, lock=lock)
        job = SimpleJob()

        runner = JobRunner(middleware_overrides=[mw])
        await runner.execute(job)
        assert job.handled is True

    async def test_releases_job_when_limit_exceeded(self) -> None:
        lock = MemoryLock()
        mw = RateLimited(key="api", max_attempts=1, decay_seconds=60, lock=lock)

        job1 = SimpleJob()
        runner = JobRunner(middleware_overrides=[mw])
        await runner.execute(job1)
        assert job1.handled is True

        job2 = SimpleJob()
        runner2 = JobRunner(middleware_overrides=[mw])
        await runner2.execute(job2)
        assert job2.handled is False  # released, not executed


# ──── AC-011: WithoutOverlapping ────


class TestWithoutOverlapping:
    async def test_allows_job_when_not_locked(self) -> None:
        lock = MemoryLock()
        mw = WithoutOverlapping(key="import-users", lock=lock)
        job = SimpleJob()
        runner = JobRunner(middleware_overrides=[mw])
        await runner.execute(job)
        assert job.handled is True

    async def test_releases_job_when_key_locked(self) -> None:
        lock = MemoryLock()
        await lock.acquire("without-overlapping:import-users", ttl=60)

        mw = WithoutOverlapping(key="import-users", lock=lock)
        job = SimpleJob()
        runner = JobRunner(middleware_overrides=[mw])
        await runner.execute(job)
        assert job.handled is False


# ──── AC-012: Middleware order ────


class TestMiddlewareOrder:
    async def test_middleware_runs_in_declared_order(self) -> None:
        log: list[str] = []
        mw_a = OrderTracker("A", log)
        mw_b = OrderTracker("B", log)

        job = SimpleJob()
        runner = JobRunner(middleware_overrides=[mw_a, mw_b])
        await runner.execute(job)

        assert log == ["before-A", "before-B", "after-B", "after-A"]
        assert job.handled is True


# ──── AC-013: Skipping middleware ────


class TestSkippingMiddleware:
    async def test_skipping_middleware_does_not_execute_job(self) -> None:
        mw = SkippingMiddleware()
        job = SimpleJob()
        runner = JobRunner(middleware_overrides=[mw])
        await runner.execute(job)
        assert job.handled is False

    async def test_skipping_middleware_does_not_mark_job_failed(self) -> None:
        mw = SkippingMiddleware()
        job = SimpleJob()
        runner = JobRunner(middleware_overrides=[mw])
        await runner.execute(job)  # should not raise
