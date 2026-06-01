"""Redis-backed cross-node fan-out (uses fakeredis)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


@pytest.fixture
def fake_redis() -> Any:
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    return fakeredis.FakeRedis()


@pytest.mark.asyncio
async def test_redis_fanout_publishes_to_all_subscribed_servers(fake_redis: Any) -> None:
    """PUBLISH by one server is received by another subscribed server."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.redis_bus import RedisBus

    config = ReverbConfig(app_id="x", key="k", secret="s")
    bus_a = RedisBus(redis=fake_redis, config=config)
    bus_b = RedisBus(redis=fake_redis, config=config)
    received: list[dict[str, object]] = []

    async def _on_message(channel: str, event: str, payload: dict[str, object]) -> None:
        del channel
        received.append({"event": event, "payload": payload})

    await bus_b.subscribe(_on_message)
    await bus_a.publish("orders", "OrderShipped", {"order_id": 42})

    # Allow event loop to deliver
    for _ in range(20):
        if received:
            break
        await asyncio.sleep(0.01)

    assert received
    assert received[0]["event"] == "OrderShipped"


@pytest.mark.asyncio
async def test_redis_bus_filters_local_origin(fake_redis: Any) -> None:
    """server doesn't re-process its own broadcasts (origin tag)."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.redis_bus import RedisBus

    config = ReverbConfig(app_id="x", key="k", secret="s")
    bus = RedisBus(redis=fake_redis, config=config)
    received: list[str] = []

    async def _on_message(channel: str, event: str, payload: dict[str, object]) -> None:
        del channel, payload
        received.append(event)

    await bus.subscribe(_on_message)
    await bus.publish("x", "X", {})

    for _ in range(20):
        await asyncio.sleep(0.01)

    assert not received  # local origin → filtered


@pytest.mark.asyncio
async def test_reverb_server_fans_out_redis_broadcasts_to_local_subscribers(
    fake_redis: Any,
) -> None:
    """events arriving on RedisBus are pushed to local WS subscribers."""
    import json

    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.redis_bus import RedisBus
    from arvel.reverb.server import ReverbServer

    from .conftest import QueueWS

    config = ReverbConfig(app_id="x", key="k", secret="s")
    bus_publisher = RedisBus(redis=fake_redis, config=config)
    bus_listener = RedisBus(redis=fake_redis, config=config)
    server = ReverbServer(config=config, redis_bus=bus_listener)

    ws = QueueWS()
    await server.start_redis_bridge()
    task = asyncio.create_task(server.handle_connection(ws))
    await ws.push(json.dumps({"event": "pusher:subscribe", "data": {"channel": "orders"}}))
    assert await ws.wait_for("subscription_succeeded")

    await bus_publisher.publish("orders", "OrderShipped", {"order_id": 42})
    assert await ws.wait_for("OrderShipped"), (
        f"Expected Redis-delivered OrderShipped frame; got {ws.sent}"
    )

    await ws.close_input()
    await task
