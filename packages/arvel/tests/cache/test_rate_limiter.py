"""Tests for RateLimiter — FR-006-013."""

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
