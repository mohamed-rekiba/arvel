"""Tests for RedisLock driver — FR-113.

Mocks the Redis client so tests run without a real Redis server.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from arvel.lock.contracts import LockContract


class TestRedisLockDriver:
    """FR-113: RedisLock implements distributed locking via Redis SET NX."""

    def _make_driver(self):
        from arvel.lock.drivers.redis_driver import RedisLock

        mock_redis = AsyncMock()
        return RedisLock(client=mock_redis), mock_redis

    def test_redis_implements_contract(self) -> None:
        from arvel.lock.drivers.redis_driver import RedisLock

        assert issubclass(RedisLock, LockContract)

    async def test_acquire_uses_set_nx(self) -> None:
        lock, redis = self._make_driver()
        redis.set.return_value = True
        result = await lock.acquire("my-lock", ttl=30, owner="worker-1")
        assert result is True
        redis.set.assert_awaited_once_with("my-lock", "worker-1", nx=True, ex=30)

    async def test_acquire_returns_false_when_held(self) -> None:
        lock, redis = self._make_driver()
        redis.set.return_value = None
        result = await lock.acquire("my-lock", ttl=30)
        assert result is False

    async def test_acquire_generates_owner_when_none(self) -> None:
        lock, redis = self._make_driver()
        redis.set.return_value = True
        await lock.acquire("my-lock", ttl=30)
        call_args = redis.set.call_args
        owner_value = call_args[0][1]
        assert isinstance(owner_value, str)
        assert len(owner_value) > 0

    async def test_release_deletes_when_owner_matches(self) -> None:
        lock, redis = self._make_driver()
        redis.get.return_value = "worker-1"
        redis.delete.return_value = 1
        result = await lock.release("my-lock", owner="worker-1")
        assert result is True

    async def test_release_raises_ownership_error(self) -> None:
        from arvel.lock.exceptions import LockOwnershipError

        lock, redis = self._make_driver()
        redis.get.return_value = "worker-1"
        with pytest.raises(LockOwnershipError):
            await lock.release("my-lock", owner="worker-2")

    async def test_release_returns_false_when_not_held(self) -> None:
        lock, redis = self._make_driver()
        redis.get.return_value = None
        result = await lock.release("my-lock")
        assert result is False

    async def test_extend_renews_ttl(self) -> None:
        lock, redis = self._make_driver()
        redis.expire.return_value = True
        result = await lock.extend("my-lock", ttl=60)
        assert result is True
        redis.expire.assert_awaited_once_with("my-lock", 60)

    async def test_extend_returns_false_when_not_held(self) -> None:
        lock, redis = self._make_driver()
        redis.expire.return_value = False
        result = await lock.extend("my-lock", ttl=60)
        assert result is False

    async def test_is_locked_returns_true(self) -> None:
        lock, redis = self._make_driver()
        redis.exists.return_value = 1
        assert await lock.is_locked("my-lock") is True

    async def test_is_locked_returns_false(self) -> None:
        lock, redis = self._make_driver()
        redis.exists.return_value = 0
        assert await lock.is_locked("my-lock") is False

    async def test_with_lock_context_manager(self) -> None:
        lock, redis = self._make_driver()
        redis.set.return_value = True
        redis.get.return_value = "auto-owner"
        redis.delete.return_value = 1

        executed = False
        async with lock.with_lock("ctx-lock", ttl=10):
            executed = True
        assert executed is True

    async def test_with_lock_raises_on_failure(self) -> None:
        from arvel.lock.exceptions import LockAcquisitionError

        lock, redis = self._make_driver()
        redis.set.return_value = None

        with pytest.raises(LockAcquisitionError):
            async with lock.with_lock("busy-lock", ttl=10):
                pass
