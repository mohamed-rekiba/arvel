"""Cache (backlog 6.3) — parity fill: events, many/put_many, lock conveniences,
increment_with_ttl. Written test-first."""

from __future__ import annotations

import asyncio

import pytest

from arvel.cache import (
    CacheHit,
    CacheManager,
    CacheMissed,
    CacheRepository,
    KeyForgotten,
    KeyWritten,
    LockAcquireFailed,
)
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application


@pytest.fixture
def cache() -> CacheRepository:
    return CacheManager().driver()


# --- events ------------------------------------------------------------------


def _bind_dispatcher() -> Dispatcher:
    app = Application()
    dispatcher = Dispatcher()
    app.instance("events", dispatcher)
    set_application(app)
    return dispatcher


async def test_get_dispatches_hit_and_missed(cache: CacheRepository) -> None:
    dispatcher = _bind_dispatcher()
    seen: list[object] = []
    dispatcher.listen(CacheHit, seen.append)
    dispatcher.listen(CacheMissed, seen.append)
    try:
        await cache.put("k", "v")
        await cache.get("k")
        await cache.get("missing")
        assert isinstance(seen[-2], CacheHit)
        assert seen[-2].key == "k"
        assert seen[-2].value == "v"
        assert isinstance(seen[-1], CacheMissed)
        assert seen[-1].key == "missing"
    finally:
        set_application(None)


async def test_put_and_forget_dispatch_written_and_forgotten(cache: CacheRepository) -> None:
    dispatcher = _bind_dispatcher()
    seen: list[object] = []
    dispatcher.listen(KeyWritten, seen.append)
    dispatcher.listen(KeyForgotten, seen.append)
    try:
        await cache.put("k", "v", ttl=60)
        await cache.forget("k")
        assert isinstance(seen[0], KeyWritten)
        assert seen[0].key == "k"
        assert seen[0].value == "v"
        assert seen[0].ttl == 60
        assert isinstance(seen[1], KeyForgotten)
        assert seen[1].key == "k"
    finally:
        set_application(None)


async def test_events_are_a_no_op_without_a_bound_app(cache: CacheRepository) -> None:
    # no application bound at all — get/put must not raise
    await cache.put("k", "v")
    assert await cache.get("k") == "v"


# --- many / put_many -----------------------------------------------------------


async def test_put_many_then_many_round_trips(cache: CacheRepository) -> None:
    assert await cache.put_many({"a": 1, "b": 2, "c": None}) is True
    result = await cache.many(["a", "b", "c", "missing"], default="d")
    assert result == {"a": 1, "b": 2, "c": None, "missing": "d"}


async def test_put_many_non_positive_ttl_stores_nothing(cache: CacheRepository) -> None:
    await cache.put("a", "existing")
    assert await cache.put_many({"a": "new"}, ttl=0) is False
    assert await cache.has("a") is False


# --- lock conveniences -----------------------------------------------------------


async def test_lock_get_runs_callback_and_releases(cache: CacheRepository) -> None:
    lock = cache.lock("L")
    result = await lock.get(lambda: "done")
    assert result == "done"
    assert await cache.lock("L").acquire() is True  # released


async def test_lock_get_releases_on_exception(cache: CacheRepository) -> None:
    lock = cache.lock("L")

    async def boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await lock.get(boom)
    assert await cache.lock("L").acquire() is True  # released despite the exception


async def test_lock_get_raises_when_already_held(cache: CacheRepository) -> None:
    holder = cache.lock("L")
    await holder.acquire()
    with pytest.raises(LockAcquireFailed):
        await cache.lock("L").get(lambda: "unreachable")


async def test_lock_block_with_callback_releases_after_running(cache: CacheRepository) -> None:
    lock = cache.lock("L")
    result = await lock.block(1, sleep=0.01, callback=lambda: "ran")
    assert result == "ran"
    assert await cache.lock("L").acquire() is True  # released


async def test_lock_refresh_extends_expiry_for_owner(cache: CacheRepository) -> None:
    lock = cache.lock("L", seconds=1)
    await lock.acquire()
    assert await lock.refresh(3) is True
    await asyncio.sleep(1.2)
    # past the original 1s TTL, well within the refreshed 3s one — refresh extended it
    assert await cache.lock("L").acquire() is False


async def test_lock_refresh_fails_for_non_owner(cache: CacheRepository) -> None:
    owner_lock = cache.lock("L")
    await owner_lock.acquire()
    impostor = cache.lock("L")
    assert await impostor.refresh(60) is False


# --- increment_with_ttl -----------------------------------------------------------


async def test_increment_with_ttl_creates_and_arms_ttl_once(cache: CacheRepository) -> None:
    assert await cache.increment_with_ttl("hits", ttl=60) == 1
    assert await cache.increment_with_ttl("hits", ttl=60) == 2
    ttl = await cache.client.get_expire("hits")
    assert ttl > 0  # armed on the creating hit


async def test_increment_with_ttl_atomic_under_concurrency(cache: CacheRepository) -> None:
    results = await asyncio.gather(
        *(cache.increment_with_ttl("counter", ttl=60) for _ in range(20))
    )
    assert sorted(results) == list(range(1, 21))  # every increment landed exactly once
