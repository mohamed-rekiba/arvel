"""Tests for unique jobs — Story 3.

AC-014: Duplicate dispatch within window is silently dropped
AC-015: Completed unique job still blocks re-dispatch within window
AC-016: unique_until_processing releases lock when processing starts
AC-017: Lock backend unavailable -> graceful degradation
"""

from __future__ import annotations

from arvel.lock.drivers.memory_driver import MemoryLock
from arvel.queue.job import Job
from arvel.queue.unique_job import UniqueJobGuard


class UniqueImportJob(Job):
    user_id: int = 42
    unique_for: int = 300
    unique_id: str = ""
    unique_until_processing: bool = False
    handled: bool = False

    async def handle(self) -> None:
        self.handled = True

    def get_unique_id(self) -> str:
        return self.unique_id or f"import-{self.user_id}"


# ──── AC-014: Duplicate dispatch dropped ────


class TestUniqueDuplicate:
    async def test_second_dispatch_within_window_is_dropped(self) -> None:
        lock = MemoryLock()
        guard = UniqueJobGuard(lock=lock)

        job1 = UniqueImportJob(user_id=42, unique_for=300)
        allowed1 = await guard.acquire(job1)
        assert allowed1 is True

        job2 = UniqueImportJob(user_id=42, unique_for=300)
        allowed2 = await guard.acquire(job2)
        assert allowed2 is False  # duplicate dropped

    async def test_different_unique_id_is_allowed(self) -> None:
        lock = MemoryLock()
        guard = UniqueJobGuard(lock=lock)

        job1 = UniqueImportJob(user_id=1, unique_for=300)
        assert await guard.acquire(job1) is True

        job2 = UniqueImportJob(user_id=2, unique_for=300)
        assert await guard.acquire(job2) is True  # different key


# ──── AC-015: Completed job still blocks within window ────


class TestUniqueAfterCompletion:
    async def test_completed_job_still_blocks_redispatch(self) -> None:
        lock = MemoryLock()
        guard = UniqueJobGuard(lock=lock)

        job = UniqueImportJob(user_id=42, unique_for=300)
        assert await guard.acquire(job) is True
        # Don't release — simulates "completed but window active"
        job2 = UniqueImportJob(user_id=42, unique_for=300)
        assert await guard.acquire(job2) is False


# ──── AC-016: unique_until_processing ────


class TestUniqueUntilProcessing:
    async def test_lock_released_when_processing_starts(self) -> None:
        lock = MemoryLock()
        guard = UniqueJobGuard(lock=lock)

        job = UniqueImportJob(user_id=42, unique_for=300, unique_until_processing=True)
        assert await guard.acquire(job) is True

        await guard.release_for_processing(job)

        job2 = UniqueImportJob(user_id=42, unique_for=300, unique_until_processing=True)
        assert await guard.acquire(job2) is True  # allowed after release


# ──── AC-017: Graceful degradation ────


class TestGracefulDegradation:
    async def test_dispatch_proceeds_when_lock_unavailable(self) -> None:

        class BrokenLock(MemoryLock):
            async def acquire(self, key: str, ttl: int, **kwargs: object) -> bool:
                raise ConnectionError("lock backend down")

        guard = UniqueJobGuard(lock=BrokenLock())
        job = UniqueImportJob(user_id=42, unique_for=300)
        allowed = await guard.acquire(job)
        assert allowed is True  # graceful degradation


class TestUniqueKeyHashing:
    async def test_unique_key_is_hashed(self) -> None:
        guard = UniqueJobGuard(lock=MemoryLock())
        job = UniqueImportJob(user_id=42, unique_for=300)
        key = guard._make_key(job)
        assert "import-42" not in key  # raw ID must not appear
        assert len(key) > 20  # hash should be substantial
