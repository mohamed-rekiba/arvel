"""Tests for LockContract and drivers — Story 5.

FR-108: LockContract ABC with acquire, release, extend, is_locked, with_lock.
FR-109: acquire(key, ttl, owner, wait) returns bool.
FR-110: release(key, owner) with ownership verification.
FR-111: extend(key, ttl) renews TTL.
FR-112: with_lock(key, ttl) async context manager.
FR-114: MemoryLock driver.
FR-115: NullLock driver.
FR-116: LockFake.
SEC-026: Lock keys not guessable/manipulable by external input.
"""

from __future__ import annotations

import pytest

from arvel.lock.contracts import LockContract
from arvel.lock.exceptions import LockAcquisitionError, LockOwnershipError


class TestLockContractInterface:
    """FR-108: LockContract ABC defines required methods."""

    def test_lock_contract_is_abstract(self) -> None:
        abstract_cls: type = LockContract
        with pytest.raises(TypeError):
            abstract_cls()

    @pytest.mark.parametrize(
        "method",
        [
            "acquire",
            "release",
            "extend",
            "is_locked",
            "with_lock",
        ],
    )
    def test_contract_has_method(self, method: str) -> None:
        assert hasattr(LockContract, method)


class TestMemoryLockDriver:
    """FR-114: MemoryLock — in-process locking."""

    async def test_memory_implements_contract(self) -> None:
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        assert isinstance(lock, LockContract)

    async def test_acquire_and_release(self) -> None:
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        acquired = await lock.acquire("job-1", ttl=30)
        assert acquired is True
        assert await lock.is_locked("job-1") is True

        released = await lock.release("job-1")
        assert released is True
        assert await lock.is_locked("job-1") is False

    async def test_acquire_already_held(self) -> None:
        """FR-109: Returns False if already held (wait=False)."""
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        await lock.acquire("exclusive", ttl=30)
        second = await lock.acquire("exclusive", ttl=30)
        assert second is False

    async def test_release_with_wrong_owner(self) -> None:
        """FR-110: Owner verification prevents releasing another's lock."""
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        await lock.acquire("protected", ttl=30, owner="process-A")

        with pytest.raises(LockOwnershipError):
            await lock.release("protected", owner="process-B")

    async def test_release_with_correct_owner(self) -> None:
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        await lock.acquire("owned", ttl=30, owner="me")
        released = await lock.release("owned", owner="me")
        assert released is True

    async def test_extend_existing_lock(self) -> None:
        """FR-111: extend(key, ttl) renews the lock TTL."""
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        await lock.acquire("extend-me", ttl=10)
        extended = await lock.extend("extend-me", ttl=60)
        assert extended is True

    async def test_extend_nonexistent_lock(self) -> None:
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        extended = await lock.extend("nope", ttl=60)
        assert extended is False

    async def test_is_locked_false_when_free(self) -> None:
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        assert await lock.is_locked("free") is False

    async def test_with_lock_context_manager(self) -> None:
        """FR-112: Async context manager acquires on entry, releases on exit."""
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        executed = False

        async with lock.with_lock("ctx", ttl=30):
            assert await lock.is_locked("ctx") is True
            executed = True

        assert executed is True
        assert await lock.is_locked("ctx") is False

    async def test_with_lock_raises_on_conflict(self) -> None:
        """FR-112: Raises LockAcquisitionError when lock cannot be acquired."""
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()
        await lock.acquire("busy", ttl=30)

        with pytest.raises(LockAcquisitionError) as exc_info:
            async with lock.with_lock("busy", ttl=30):
                pass  # pragma: no cover

        assert exc_info.value.key == "busy"

    async def test_with_lock_releases_on_exception(self) -> None:
        from arvel.lock.drivers.memory_driver import MemoryLock

        lock = MemoryLock()

        with pytest.raises(RuntimeError, match="oops"):
            async with lock.with_lock("fragile", ttl=30):
                raise RuntimeError("oops")

        assert await lock.is_locked("fragile") is False


class TestNullLockDriver:
    """FR-115: NullLock always succeeds (no-op locking)."""

    async def test_null_implements_contract(self) -> None:
        from arvel.lock.drivers.null_driver import NullLock

        lock = NullLock()
        assert isinstance(lock, LockContract)

    async def test_null_acquire_always_true(self) -> None:
        from arvel.lock.drivers.null_driver import NullLock

        lock = NullLock()
        assert await lock.acquire("any", ttl=30) is True

    async def test_null_release_always_true(self) -> None:
        from arvel.lock.drivers.null_driver import NullLock

        lock = NullLock()
        assert await lock.release("any") is True

    async def test_null_is_locked_always_false(self) -> None:
        from arvel.lock.drivers.null_driver import NullLock

        lock = NullLock()
        assert await lock.is_locked("any") is False


class TestLockFake:
    """FR-116: LockFake captures lock operations for assertion."""

    async def test_fake_implements_contract(self) -> None:
        from arvel.lock.fakes import LockFake

        fake = LockFake()
        assert isinstance(fake, LockContract)

    async def test_fake_records_acquire(self) -> None:
        from arvel.lock.fakes import LockFake

        fake = LockFake()
        await fake.acquire("job", ttl=30)
        fake.assert_acquired("job")

    async def test_fake_assert_nothing_acquired(self) -> None:
        from arvel.lock.fakes import LockFake

        fake = LockFake()
        fake.assert_nothing_acquired()


class TestLockExceptions:
    """Exception attribute coverage."""

    def test_acquisition_error(self) -> None:
        err = LockAcquisitionError("my-key")
        assert err.key == "my-key"
        assert "my-key" in str(err)

    def test_ownership_error(self) -> None:
        err = LockOwnershipError("my-key", "owner-A", "owner-B")
        assert err.key == "my-key"
        assert err.expected_owner == "owner-A"
        assert err.actual_owner == "owner-B"
        assert "owner-A" in str(err)
        assert "owner-B" in str(err)


class TestLockConfig:
    """NFR-038: LockSettings uses LOCK_ env prefix."""

    def test_defaults(self, clean_env: None) -> None:
        from arvel.lock.config import LockSettings

        settings = LockSettings()
        assert settings.driver == "memory"
        assert settings.default_ttl == 30
