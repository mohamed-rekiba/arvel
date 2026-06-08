"""Tests for RateLimiter."""

from __future__ import annotations

import pytest
from arvel.cache import CacheManager
from arvel.cache.rate_limiter import RateLimiter
from arvel.config.cache_config import CacheConfig, CacheDriver


@pytest.fixture
def manager() -> CacheManager:
    return CacheManager(CacheConfig(connection=CacheDriver.ARRAY))


@pytest.fixture
def limiter(manager: CacheManager) -> RateLimiter:
    return manager.rate_limiter()


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_attempt_within_limit(self, limiter: RateLimiter) -> None:
        for _ in range(5):
            allowed = await limiter.attempt("ip:1.1.1.1", max_attempts=10, decay=60)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_attempt_exceeds_limit(self, limiter: RateLimiter) -> None:
        for _ in range(5):
            await limiter.attempt("ip:2.2.2.2", max_attempts=5, decay=60)

        # 6th attempt should be denied
        allowed = await limiter.attempt("ip:2.2.2.2", max_attempts=5, decay=60)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_remaining_decrements(self, limiter: RateLimiter) -> None:
        key = "ip:3.3.3.3"
        await limiter.attempt(key, max_attempts=5, decay=60)
        remaining = await limiter.remaining(key, max_attempts=5)
        assert remaining == 4

    @pytest.mark.asyncio
    async def test_remaining_zero_after_exhausted(self, limiter: RateLimiter) -> None:
        key = "ip:4.4.4.4"
        for _ in range(5):
            await limiter.attempt(key, max_attempts=5, decay=60)
        remaining = await limiter.remaining(key, max_attempts=5)
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_reset_clears_count(self, limiter: RateLimiter) -> None:
        key = "ip:5.5.5.5"
        for _ in range(5):
            await limiter.attempt(key, max_attempts=5, decay=60)
        await limiter.reset(key)
        remaining = await limiter.remaining(key, max_attempts=5)
        assert remaining == 5

    @pytest.mark.asyncio
    async def test_different_keys_independent(self, limiter: RateLimiter) -> None:
        for _ in range(5):
            await limiter.attempt("ip:6.6.6.6", max_attempts=5, decay=60)

        # Different key is unaffected
        allowed = await limiter.attempt("ip:7.7.7.7", max_attempts=5, decay=60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_window_is_fixed_not_sliding(
        self, limiter: RateLimiter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The window is anchored to the first hit. A later in-window hit must NOT
        # extend it (the old code reset the TTL on every hit -> sliding window).
        # ArrayStore expiry uses time.monotonic, so patching time.time is isolated.
        import time

        clock = {"now": 1000.0}
        monkeypatch.setattr(time, "time", lambda: clock["now"])
        key = "ip:8.8.8.8"

        assert await limiter.attempt(key, max_attempts=2, decay=60) is True  # t=1000, window->1060
        clock["now"] = 1040.0
        # 2nd hit within the window — window must stay anchored at 1060.
        assert await limiter.attempt(key, max_attempts=2, decay=60) is True
        clock["now"] = 1050.0
        # Capped, still inside the original window.
        assert await limiter.attempt(key, max_attempts=2, decay=60) is False

        # Past the original window: a sliding limiter would still block here.
        clock["now"] = 1061.0
        assert await limiter.attempt(key, max_attempts=2, decay=60) is True
        assert await limiter.remaining(key, max_attempts=2) == 1

    @pytest.mark.asyncio
    async def test_remaining_resets_after_window(
        self, limiter: RateLimiter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        clock = {"now": 5000.0}
        monkeypatch.setattr(time, "time", lambda: clock["now"])
        key = "ip:9.9.9.9"

        await limiter.attempt(key, max_attempts=3, decay=30)
        assert await limiter.remaining(key, max_attempts=3) == 2

        clock["now"] = 5031.0  # window elapsed
        assert await limiter.remaining(key, max_attempts=3) == 3
