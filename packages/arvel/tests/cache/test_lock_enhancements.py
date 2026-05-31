"""Epic 001 Story 8 — cache lock enhancements (extend, backoff, fake)."""

from __future__ import annotations

import warnings
from itertools import pairwise

import pytest
from arvel.cache import CacheManager
from arvel.config.cache_config import CacheConfig, CacheDriver
from arvel.testing.fakes import LockFake


@pytest.fixture
def manager() -> CacheManager:
    return CacheManager(CacheConfig(connection=CacheDriver.ARRAY))


async def test_extend_renews_ttl_for_owner(manager: CacheManager) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        lock = manager.lock("job:import", ttl=60)
        assert await lock.acquire() is True
        assert await lock.extend(120) is True


async def test_extend_by_non_owner_returns_false(manager: CacheManager) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        holder = manager.lock("job:shared", ttl=60)
        assert await holder.acquire() is True

        other = manager.lock("job:shared", ttl=60)
        assert await other.extend(120) is False


async def test_block_uses_exponential_backoff(
    manager: CacheManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []

    async def _fake_sleep(d: float) -> None:
        delays.append(d)

    monkeypatch.setattr("arvel.cache.locks.asyncio.sleep", _fake_sleep)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        held = manager.lock("job:busy", ttl=60)
        assert await held.acquire() is True

        waiter = manager.lock("job:busy", ttl=60)
        acquired = await waiter.block(timeout=0.001, backoff=0.1, max_backoff=2.0)

    assert acquired is False
    # Each recorded delay must double the previous one, capped at max_backoff.
    for prev, nxt in pairwise(delays):
        assert nxt == min(prev * 2, 2.0)


def test_non_redis_store_emits_runtime_warning(manager: CacheManager) -> None:
    with pytest.warns(RuntimeWarning, match="distributed-lock"):
        manager.lock("job:warn")


async def test_lock_fake_assert_acquired() -> None:
    fake = LockFake("job:fake")
    assert await fake.acquire() is True
    fake.assert_acquired("job:fake")


async def test_lock_fake_assert_nothing_acquired() -> None:
    fake = LockFake("job:fake", succeeds=False)
    assert await fake.acquire() is False
    fake.assert_nothing_acquired()
    with pytest.raises(AssertionError):
        fake.assert_acquired()
