"""Queues (doc 12/18) — ShouldBeUnique: at most one instance of a job (class + unique_id()) may
be queued/running at a time, guarded by a story-06 CacheLock acquired before dispatch."""

from __future__ import annotations

import asyncio

from taskiq import InMemoryBroker

from arvel.cache.provider import CacheServiceProvider
from arvel.kernel import Application, set_application
from arvel.queue import Job, QueueManager
from arvel.queue.middleware import ShouldBeUnique

RUN: list[int] = []


class UniqueJob(ShouldBeUnique, Job):
    unique_for = 3600

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id

    def unique_id(self) -> str:
        return str(self.order_id)

    async def handle(self) -> None:
        RUN.append(self.order_id)


async def _manager(*, await_inplace: bool) -> QueueManager:
    app = Application()
    CacheServiceProvider(app).register()
    manager = QueueManager(app, broker=InMemoryBroker(await_inplace=await_inplace))
    app.instance("queue", manager)
    set_application(app)
    return manager


async def test_second_dispatch_within_the_window_is_suppressed() -> None:
    await _manager(await_inplace=False)  # don't run the job — prove suppression at dispatch time
    try:
        first = await UniqueJob.dispatch(1)
        second = await UniqueJob.dispatch(1)
        assert first is not None
        assert second is None  # already queued — silently dropped
    finally:
        set_application(None)


async def test_a_different_unique_id_is_not_suppressed() -> None:
    await _manager(await_inplace=False)
    try:
        first = await UniqueJob.dispatch(1)
        second = await UniqueJob.dispatch(2)  # a different order — its own uniqueness slot
        assert first is not None
        assert second is not None
    finally:
        set_application(None)


async def test_a_new_dispatch_enqueues_again_once_unique_for_elapses() -> None:
    UniqueJob.unique_for = 0  # already-expired TTL — mirrors CacheLock's own zero-TTL semantics
    try:
        await _manager(await_inplace=False)
        try:
            first = await UniqueJob.dispatch(1)
            await asyncio.sleep(0.01)
            second = await UniqueJob.dispatch(1)
            assert first is not None
            assert second is not None
        finally:
            set_application(None)
    finally:
        UniqueJob.unique_for = 3600


async def test_lock_releases_once_the_worker_finishes_processing() -> None:
    """Proves the lock is freed on completion — not just via its (here, long) TTL."""
    RUN.clear()
    await _manager(await_inplace=True)  # runs each dispatch to completion inline
    try:
        first = await UniqueJob.dispatch(1)
        second = await UniqueJob.dispatch(1)  # the window is still open, but processing released it
        assert first is not None
        assert second is not None
        assert RUN == [1, 1]
    finally:
        set_application(None)
