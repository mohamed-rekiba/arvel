"""Queues (doc 12/18) — job middleware: the onion `Pipeline` runs `job.middleware()` around
`handle()`; `WithoutOverlapping`/`RateLimited`/`ThrottlesExceptions` release the job back onto the
queue (`JobShouldBeReleased`) instead of running it, when their guard says not yet."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from taskiq import InMemoryBroker

from arvel.cache.provider import CacheServiceProvider
from arvel.http.rate_limiter import RateLimiter
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueueManager
from arvel.queue.middleware import (
    JobShouldBeReleased,
    RateLimited,
    ThrottlesExceptions,
    WithoutOverlapping,
)

ORDER: list[str] = []


class Track:
    """A tracking onion pipe — proves middleware order (before → next → after), nested."""

    def __init__(self, label: str) -> None:
        self.label = label

    async def handle(self, job: Any, next_: Any) -> Any:
        ORDER.append(f"{self.label}-before")
        result = await next_(job)
        ORDER.append(f"{self.label}-after")
        return result


class MiddlewareJob(Job):
    def middleware(self) -> list[Any]:
        return [Track("a"), Track("b")]

    async def handle(self) -> None:
        ORDER.append("handle")


async def test_job_middleware_pipeline_runs_in_onion_order() -> None:
    ORDER.clear()
    manager = QueueManager(Application(), broker=InMemoryBroker(await_inplace=True))
    await manager._worker._invoke(MiddlewareJob())
    assert ORDER == ["a-before", "b-before", "handle", "b-after", "a-after"]


async def test_a_job_with_no_middleware_still_runs() -> None:
    class Plain(Job):
        async def handle(self) -> None:
            ORDER.append("plain")

    ORDER.clear()
    manager = QueueManager(Application(), broker=InMemoryBroker(await_inplace=True))
    await manager._worker._invoke(Plain())
    assert ORDER == ["plain"]


async def test_rate_limited_defers_over_the_limit() -> None:
    app = Application()
    CacheServiceProvider(app).register()
    set_application(app)
    try:
        limiter = RateLimiter(app.make("cache"))
        middleware = RateLimited(limiter, "shared", max_attempts=2, decay_seconds=30)
        calls: list[str] = []

        async def _next(_job: Any) -> None:
            calls.append("ran")

        await middleware.handle(None, _next)
        await middleware.handle(None, _next)
        assert calls == ["ran", "ran"]

        with pytest.raises(JobShouldBeReleased):
            await middleware.handle(None, _next)
        assert calls == ["ran", "ran"]  # the 3rd never reaches `next_` — deferred instead
    finally:
        set_application(None)


class _YieldingLimiter:
    """A fake limiter with a REAL suspension point (`asyncio.sleep(0)`) wherever a real network
    round trip would be — the in-process ``RateLimiter``/array cache has none, so a concurrency
    test against it never actually interleaves (asyncio never yields control, so it's a vacuous
    test: it'd pass even on the old non-atomic code). This models a real redis-backed limiter
    instead: ``too_many_attempts``/``hit`` are each their OWN round trip (no server-side atomicity
    spans across two separate commands — the TOCTOU window is real), while ``hit_with_ttl`` is
    a SINGLE round trip (redis's own single-threaded command execution makes one INCR atomic even
    though it still has network latency) — modeled with a lock around its own read+write so it
    stays one opaque step, same guarantee a real redis server gives for free."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._hit_with_ttl_lock = asyncio.Lock()

    async def too_many_attempts(self, key: str, max_attempts: int) -> bool:
        await asyncio.sleep(0)  # round trip #1 — a concurrent caller can interleave here
        return self._counts.get(key, 0) >= max_attempts

    async def hit(self, key: str, decay_seconds: int = 60) -> int:
        await asyncio.sleep(0)  # round trip #2 — separate from too_many_attempts's
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def hit_with_ttl(self, key: str, decay_seconds: int = 60) -> int:
        # signature matches the real RateLimiter.hit_with_ttl(key, decay_seconds) exactly — it's
        # what RateLimited.handle() actually calls positionally, amount is always 1 internally.
        async with self._hit_with_ttl_lock:  # ONE round trip, atomic like a real redis INCR
            await asyncio.sleep(0)
            self._counts[key] = self._counts.get(key, 0) + 1
            return self._counts[key]

    async def available_in(self, key: str) -> int:
        return 60


async def _naive_check_then_hit(limiter: _YieldingLimiter, key: str, max_attempts: int) -> bool:
    """The OLD `RateLimited.handle()` logic (pre-fix), reproduced standalone: two separate awaited
    calls with a real gap between them. Returns whether this attempt got through."""
    if await limiter.too_many_attempts(key, max_attempts):
        return False
    await limiter.hit(key)
    return True


async def test_naive_check_then_hit_over_admits_under_a_real_toctou_window() -> None:
    """Proves the window the fix closes is real: against a limiter with a genuine suspension
    point between check and increment, firing 10 concurrent naive attempts at max_attempts=3 lets
    MORE than 3 through — the old bug, reproduced on demand."""
    limiter = _YieldingLimiter()
    results = await asyncio.gather(
        *(_naive_check_then_hit(limiter, "k", max_attempts=3) for _ in range(10))
    )
    admitted = results.count(True)
    assert admitted > 3, f"expected the naive check-then-hit race to over-admit, got {admitted}"


async def test_rate_limited_caps_exactly_at_max_attempts_under_concurrency() -> None:
    """The FIXED `RateLimited.handle()` (atomic `hit_with_ttl`), run against the SAME yielding
    limiter that just proved the naive logic over-admits — 10 concurrent attempts at
    max_attempts=3 must let through EXACTLY 3, not more."""
    limiter = _YieldingLimiter()
    middleware = RateLimited(limiter, "concurrent-key", max_attempts=3, decay_seconds=30)
    calls: list[str] = []

    async def _next(_job: Any) -> None:
        calls.append("ran")

    async def _attempt() -> str:
        try:
            await middleware.handle(None, _next)
        except JobShouldBeReleased:
            return "released"
        return "ran"

    results = await asyncio.gather(*(_attempt() for _ in range(10)))
    assert results.count("ran") == 3
    assert results.count("released") == 7
    assert len(calls) == 3


async def test_throttles_exceptions_short_circuits_after_the_cap() -> None:
    app = Application()
    CacheServiceProvider(app).register()
    set_application(app)
    try:
        middleware = ThrottlesExceptions(max_exceptions=2, decay_seconds=60, key="t")
        calls = 0

        async def _next(_job: Any) -> None:
            nonlocal calls
            calls += 1
            raise ValueError("boom")

        for _ in range(2):
            with pytest.raises(ValueError):
                await middleware.handle(None, _next)
        assert calls == 2

        with pytest.raises(JobShouldBeReleased):
            await middleware.handle(None, _next)
        assert calls == 2  # short-circuited — `next_`/`handle()` never called the 3rd time
    finally:
        set_application(None)


ORDER2: list[str] = []


class SlowOverlapping(Job):
    """`handle()` holds the `WithoutOverlapping` lock for a bit — long enough for a second,
    overlapping dispatch to find it held."""

    def __init__(self, label: str, key: str) -> None:
        self.label = label
        self._key = key

    def middleware(self) -> list[Any]:
        return [WithoutOverlapping(self._key, expire=5, release_after=0.02)]

    async def handle(self) -> None:
        ORDER2.append(f"{self.label}-start")
        await asyncio.sleep(0.1)
        ORDER2.append(f"{self.label}-end")


async def test_without_overlapping_serializes_two_overlapping_jobs() -> None:
    ORDER2.clear()
    app = Application()
    CacheServiceProvider(app).register()
    manager = QueueManager(app, broker=InMemoryBroker())
    app.instance("queue", manager)
    set_application(app)
    try:
        await manager.push_instance(SlowOverlapping("a", "shared"))
        await asyncio.sleep(0.02)  # let "a" acquire the lock and start its slow handle() first
        await manager.push_instance(SlowOverlapping("b", "shared"))  # overlaps -> released, retried

        expected = ["a-start", "a-end", "b-start", "b-end"]
        for _ in range(150):
            if expected == ORDER2:
                break
            await asyncio.sleep(0.02)
        assert expected == ORDER2  # never interleaved — "b" only ran after "a" released the lock
    finally:
        set_application(None)
