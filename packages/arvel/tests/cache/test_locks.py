"""Tests for CacheLock."""

from __future__ import annotations

import asyncio

import pytest
from arvel.cache import CacheManager
from arvel.config.cache_config import CacheConfig, CacheDriver


@pytest.fixture
def manager() -> CacheManager:
    return CacheManager(CacheConfig(connection=CacheDriver.ARRAY))


class TestCacheLockAcquireRelease:
    @pytest.mark.asyncio
    async def test_lock_acquired_via_context_manager(self, manager: CacheManager) -> None:
        async with manager.lock("test:lock", ttl=60) as acquired:
            assert acquired is True

    @pytest.mark.asyncio
    async def test_lock_not_reacquired_while_held(self, manager: CacheManager) -> None:
        async with manager.lock("test:exclusive", ttl=60) as acquired:
            assert acquired is True
            async with manager.lock("test:exclusive", ttl=60) as acquired2:
                assert acquired2 is False

    @pytest.mark.asyncio
    async def test_lock_released_on_context_exit(self, manager: CacheManager) -> None:
        async with manager.lock("test:released", ttl=60):
            pass
        # Can re-acquire after release
        async with manager.lock("test:released", ttl=60) as acquired:
            assert acquired is True

    @pytest.mark.asyncio
    async def test_lock_released_on_exception(self, manager: CacheManager) -> None:
        try:
            async with manager.lock("test:exc", ttl=60):
                raise ValueError("boom")
        except ValueError:
            pass
        # Lock must be released after exception
        async with manager.lock("test:exc", ttl=60) as acquired:
            assert acquired is True

    @pytest.mark.asyncio
    async def test_explicit_release(self, manager: CacheManager) -> None:
        lock = manager.lock("test:manual", ttl=60)
        acquired = await lock.acquire()
        assert acquired is True
        await lock.release()
        acquired2 = await lock.acquire()
        assert acquired2 is True


class TestCacheLockBlock:
    @pytest.mark.asyncio
    async def test_block_waits_and_acquires(self, manager: CacheManager) -> None:
        """block() polls until lock is available."""
        # Acquire the lock, then release it after 0.1s
        lock_held = asyncio.Event()
        lock_released = asyncio.Event()

        async def holder() -> None:
            async with manager.lock("test:block_target", ttl=10) as acquired:
                assert acquired
                lock_held.set()
                await asyncio.sleep(0.05)
            lock_released.set()

        asyncio.create_task(holder())
        await lock_held.wait()

        lock = manager.lock("test:block_target", ttl=10)
        result = await lock.block(timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_block_times_out_if_lock_not_released(self, manager: CacheManager) -> None:
        async with manager.lock("test:timeout_lock", ttl=60):
            lock = manager.lock("test:timeout_lock", ttl=60)
            result = await lock.block(timeout=0.05)
            assert result is False
