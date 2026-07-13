"""Integration (spec 19 §1, story 06) — the redis broadcast driver: a real publish/subscribe
round-trip over Valkey/Redis (story-06's redis facade), including the ``to_others()`` exclusion
payload."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from arvel.broadcasting import InteractsWithSockets, RedisBroadcaster, accepts
from arvel.cache.redis import RedisManager
from arvel.events.dispatcher import ShouldBroadcast

pytestmark = pytest.mark.integration


class OrderShipped(ShouldBroadcast, InteractsWithSockets):
    def broadcast_on(self) -> list[Any]:
        return ["orders"]

    def broadcast_with(self) -> dict[str, Any]:
        return {"order_id": 42}


async def test_redis_broadcast_publish_round_trips_over_real_valkey(
    redis_url: str, configure_app: Any
) -> None:
    app = configure_app(redis={"url": redis_url})
    redis_manager = RedisManager(app)
    app.instance("redis", redis_manager)
    try:
        received: list[str] = []

        async def consume() -> None:
            async for message in redis_manager.connection().subscribe("arvel.broadcasting.orders"):
                received.append(message)
                break

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.2)
        await RedisBroadcaster(app).broadcast(OrderShipped())
        await asyncio.wait_for(consumer, timeout=5)

        payload = json.loads(received[0])
        assert payload == {
            "event": "OrderShipped",
            "data": {"order_id": 42},
            "except_socket_id": None,
        }
    finally:
        await redis_manager.close_all()


async def test_to_others_exclusion_is_observed_by_two_subscribers_over_real_valkey(
    redis_url: str, configure_app: Any
) -> None:
    """One published message; two (simulated) subscriber sockets independently decide whether to
    accept it — the triggering socket skips its own echo, every other socket still gets it."""
    app = configure_app(redis={"url": redis_url})
    redis_manager = RedisManager(app)
    app.instance("redis", redis_manager)
    try:
        received: list[str] = []

        async def consume() -> None:
            async for message in redis_manager.connection().subscribe("arvel.broadcasting.orders"):
                received.append(message)
                break

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.2)
        event = OrderShipped().to_others("socket-A")
        await RedisBroadcaster(app).broadcast(event)
        await asyncio.wait_for(consumer, timeout=5)

        payload = json.loads(received[0])
        assert accepts(payload, "socket-A") is False  # the sender's own connection: skipped
        assert accepts(payload, "socket-B") is True  # a different connected client: delivered
    finally:
        await redis_manager.close_all()
