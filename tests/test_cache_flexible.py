"""Cache (spec 06-cache-parity §1) — `flexible()` stale-while-revalidate, with an injected clock
so the fresh/stale windows are observed deterministically (no real sleeps)."""

from __future__ import annotations

import asyncio
from typing import Any

from arvel.cache import CacheManager


def _cache() -> Any:
    return CacheManager().driver()


class _FakeClock:
    """A controllable clock: advance it explicitly instead of sleeping in real time."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_flexible_serves_cached_value_within_fresh_window() -> None:
    cache = _cache()
    clock = _FakeClock()
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return 42

    assert await cache.flexible("k", (10, 30), compute, clock=clock) == 42
    clock.advance(5)  # still within fresh (<=10)
    assert await cache.flexible("k", (10, 30), compute, clock=clock) == 42
    assert calls["n"] == 1  # never recomputed


async def test_flexible_serves_stale_and_revalidates_once_in_background() -> None:
    cache = _cache()
    clock = _FakeClock()
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return calls["n"]

    assert await cache.flexible("k", (10, 30), compute, clock=clock) == 1
    clock.advance(15)  # past fresh (10), within stale (30)

    # two concurrent stale hits: both see the stale value, only one revalidates (single-flight)
    results = await asyncio.gather(
        cache.flexible("k", (10, 30), compute, clock=clock),
        cache.flexible("k", (10, 30), compute, clock=clock),
    )
    assert list(results) == [1, 1]  # stale value served, not yet refreshed
    await cache.wait_for_pending_revalidations()
    assert calls["n"] == 2  # exactly one background revalidation ran

    clock.advance(0)  # now within fresh of the refreshed value
    assert await cache.flexible("k", (10, 30), compute, clock=clock) == 2


async def test_flexible_recomputes_inline_past_stale() -> None:
    cache = _cache()
    clock = _FakeClock()
    calls = {"n": 0}

    async def compute() -> int:
        calls["n"] += 1
        return calls["n"]

    assert await cache.flexible("k", (10, 30), compute, clock=clock) == 1
    clock.advance(31)  # past stale
    assert await cache.flexible("k", (10, 30), compute, clock=clock) == 2
    assert calls["n"] == 2  # recomputed inline, not served stale


async def test_flexible_recomputes_on_miss() -> None:
    cache = _cache()
    clock = _FakeClock()

    async def compute() -> str:
        return "computed"

    assert await cache.flexible("missing", (10, 30), compute, clock=clock) == "computed"
