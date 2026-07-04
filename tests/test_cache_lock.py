"""Cache (spec 06-cache-parity §2) — CacheLock: acquire/block/release/force_release/owner/
restore_lock, and contention between two tasks on the array driver."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from arvel.cache import CacheManager, LockAcquireFailed, LockTimeout


def _cache() -> Any:
    return CacheManager().driver()


async def test_acquire_then_release() -> None:
    cache = _cache()
    lock = cache.lock("L")
    assert await lock.acquire() is True
    assert await lock.release() is True


async def test_second_holder_cannot_acquire_while_held() -> None:
    cache = _cache()
    first = cache.lock("L")
    second = cache.lock("L")
    assert await first.acquire() is True
    assert await second.acquire() is False


async def test_context_manager_raises_when_already_held() -> None:
    cache = _cache()
    holder = cache.lock("L")
    await holder.acquire()
    with pytest.raises(LockAcquireFailed):
        async with cache.lock("L"):
            pass  # pragma: no cover - never reached


async def test_context_manager_releases_on_exit() -> None:
    cache = _cache()
    async with cache.lock("L") as lock:
        assert lock.owner()
    # released → a fresh lock can now acquire it
    assert await cache.lock("L").acquire() is True


async def test_non_owner_cannot_release() -> None:
    cache = _cache()
    owner_lock = cache.lock("L")
    await owner_lock.acquire()
    impostor = cache.lock("L")  # a different owner token, same name
    assert await impostor.release() is False
    # still held by the real owner
    assert await owner_lock.release() is True


async def test_force_release_frees_regardless_of_owner() -> None:
    cache = _cache()
    owner_lock = cache.lock("L")
    await owner_lock.acquire()
    impostor = cache.lock("L")
    await impostor.force_release()
    assert await cache.lock("L").acquire() is True


async def test_restore_lock_recreates_handle_for_stored_owner() -> None:
    cache = _cache()
    original = cache.lock("L")
    await original.acquire()
    restored = cache.restore_lock("L", original.owner())
    assert restored.owner() == original.owner()
    assert await restored.release() is True
    assert await cache.lock("L").acquire() is True  # released


async def test_block_acquires_once_released_within_wait() -> None:
    cache = _cache()
    holder = cache.lock("L")
    await holder.acquire()

    async def release_soon() -> None:
        await asyncio.sleep(0.05)
        await holder.release()

    waiter = cache.lock("L")
    release_task = asyncio.create_task(release_soon())
    await waiter.block(2, sleep=0.02)  # acquires once the holder releases
    await release_task
    assert await waiter.release() is True


async def test_block_raises_lock_timeout() -> None:
    cache = _cache()
    holder = cache.lock("L")
    await holder.acquire()
    waiter = cache.lock("L")
    with pytest.raises(LockTimeout):
        await waiter.block(0.05, sleep=0.02)


async def test_contention_between_two_tasks_only_one_wins() -> None:
    """Two coroutines racing for the same lock: exactly one acquires."""
    cache = _cache()

    async def try_acquire() -> Any:
        return await cache.lock("contended").acquire()

    results = await asyncio.gather(try_acquire(), try_acquire())
    assert results.count(True) == 1
    assert results.count(False) == 1


async def test_lock_expires_after_seconds() -> None:
    cache = _cache()
    short = cache.lock("L", seconds=0)  # already-expired TTL semantics: expires immediately
    await short.acquire()
    # a lock with an effectively-zero TTL should not block a new acquirer for long
    await asyncio.sleep(0.01)
    assert await cache.lock("L").acquire() is True
