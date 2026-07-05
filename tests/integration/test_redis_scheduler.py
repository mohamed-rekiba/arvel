"""Integration (doc 12/18 — A3) — the scheduler's `on_one_server` over a real Valkey: two separate
`Schedule()` instances (standing in for two `schedule:run` processes) share one Valkey-backed
cache; exactly one of them runs a shared `on_one_server()` event's tick, arbitrated by a real
distributed lock (not the in-process array driver)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from arvel.cache import CacheManager

pytestmark = pytest.mark.integration


async def test_one_server_runs_on_exactly_one_of_two_schedulers_over_valkey(
    redis_url: str, configure_app: Any
) -> None:
    from arvel.queue.scheduler import Schedule

    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")
    ran: list[str] = []

    async def _tick() -> None:
        await asyncio.sleep(0.2)  # long enough for a second, concurrent scheduler to contend
        ran.append("ran")

    scheduler_a = Schedule(cache=cache)
    scheduler_b = Schedule(cache=cache)
    event_a = scheduler_a.call(_tick).every_minute().on_one_server().name("shared-report")
    event_b = scheduler_b.call(_tick).every_minute().on_one_server().name("shared-report")

    await asyncio.gather(event_a.run(), event_b.run())
    assert ran == ["ran"]  # only one of the two schedulers actually ran it


async def test_without_overlapping_over_valkey_skips_a_tick_in_flight(
    redis_url: str, configure_app: Any
) -> None:
    from arvel.queue.scheduler import Schedule

    app = configure_app(cache={"default": "redis", "url": redis_url})
    cache = CacheManager(app).driver("redis")
    ran: list[str] = []

    async def _slow() -> None:
        ran.append("start")
        await asyncio.sleep(0.2)
        ran.append("end")

    event = Schedule(cache=cache).call(_slow).every_minute().without_overlapping(60).name("nightly")

    first = asyncio.create_task(event.run())
    await asyncio.sleep(0.05)  # let the first tick acquire the (Valkey) lock and start
    await event.run()  # a second tick while the first is still in flight -> skipped
    await first
    assert ran == ["start", "end"]  # never two concurrent starts
