"""Tests for LockBackend implementations — InMemory and Null."""

from __future__ import annotations

from arvel.scheduler.locks import InMemoryLockBackend, NullLockBackend


class TestInMemoryLockBackend:
    """ADR-018: InMemory lock for single-process testing."""

    async def test_acquire_returns_true_when_unlocked(self) -> None:
        lock = InMemoryLockBackend()
        assert await lock.acquire("key", ttl=60) is True

    async def test_acquire_returns_false_when_locked(self) -> None:
        lock = InMemoryLockBackend()
        await lock.acquire("key", ttl=60)
        assert await lock.acquire("key", ttl=60) is False

    async def test_release_allows_reacquire(self) -> None:
        lock = InMemoryLockBackend()
        await lock.acquire("key", ttl=60)
        await lock.release("key")
        assert await lock.acquire("key", ttl=60) is True

    async def test_is_locked_true(self) -> None:
        lock = InMemoryLockBackend()
        await lock.acquire("key", ttl=60)
        assert await lock.is_locked("key") is True

    async def test_is_locked_false(self) -> None:
        lock = InMemoryLockBackend()
        assert await lock.is_locked("key") is False

    async def test_expired_lock_can_be_reacquired(self) -> None:
        lock = InMemoryLockBackend()
        await lock.acquire("key", ttl=0)
        assert await lock.acquire("key", ttl=60) is True

    async def test_release_nonexistent_key_is_noop(self) -> None:
        lock = InMemoryLockBackend()
        await lock.release("nonexistent")

    async def test_independent_keys(self) -> None:
        lock = InMemoryLockBackend()
        await lock.acquire("a", ttl=60)
        assert await lock.acquire("b", ttl=60) is True


class TestNullLockBackend:
    """ADR-018: Null lock always succeeds (overlap prevention disabled)."""

    async def test_acquire_always_true(self) -> None:
        lock = NullLockBackend()
        assert await lock.acquire("key", ttl=60) is True

    async def test_is_locked_always_false(self) -> None:
        lock = NullLockBackend()
        assert await lock.is_locked("key") is False

    async def test_release_is_noop(self) -> None:
        lock = NullLockBackend()
        await lock.release("key")
