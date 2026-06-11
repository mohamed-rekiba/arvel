"""Redis-backed cross-process fan-out (uses fakeredis).

Contract under test (ADR-013 §4): ``RedisBroadcaster`` PUBLISHes per channel
under ``arvel.broadcasting.<channel>``; a ``RedisBus`` PSUBSCRIBEd to
``arvel.broadcasting.*`` receives each message and a ``ReverbServer`` fans it
out to local subscribers, honouring ``except_socket_id``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest


@pytest.fixture
def fake_redis() -> Any:
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    return fakeredis.FakeRedis()


@pytest.mark.asyncio
async def test_bus_receives_what_broadcaster_publishes(fake_redis: Any) -> None:
    """A RedisBroadcaster PUBLISH lands on a RedisBus subscriber with the channel decoded."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.broadcasting.drivers.redis import RedisBroadcaster
    from arvel.reverb.redis_bus import RedisBus

    config = ReverbConfig(app_id="x", key="k", secret="s")
    bus = RedisBus(redis=fake_redis, config=config)
    received: list[tuple[str, str, dict[str, object], str | None]] = []

    async def _on_message(
        channel: str, event: str, payload: dict[str, object], except_socket_id: str | None
    ) -> None:
        received.append((channel, event, payload, except_socket_id))

    await bus.subscribe(_on_message)

    broadcaster = RedisBroadcaster(redis=fake_redis)
    await broadcaster.broadcast(
        ["orders"], "OrderShipped", {"order_id": 42}, except_socket_id="1.2"
    )

    for _ in range(20):
        if received:
            break
        await asyncio.sleep(0.01)

    assert received == [("orders", "OrderShipped", {"order_id": 42}, "1.2")]


@pytest.mark.asyncio
async def test_bus_ignores_unrelated_channels(fake_redis: Any) -> None:
    """A PUBLISH outside arvel.broadcasting.* is not delivered."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.redis_bus import RedisBus

    config = ReverbConfig(app_id="x", key="k", secret="s")
    bus = RedisBus(redis=fake_redis, config=config)
    received: list[str] = []

    async def _on_message(
        channel: str, event: str, payload: dict[str, object], _e: str | None
    ) -> None:
        del channel, payload
        received.append(event)

    await bus.subscribe(_on_message)
    await fake_redis.publish("some.other.channel", json.dumps({"event": "X", "data": {}}))

    for _ in range(20):
        await asyncio.sleep(0.01)

    assert not received


@pytest.mark.asyncio
async def test_reverb_server_fans_out_redis_broadcasts_to_local_subscribers(
    fake_redis: Any,
) -> None:
    """Events published via RedisBroadcaster reach a locally subscribed WS."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.broadcasting.drivers.redis import RedisBroadcaster
    from arvel.reverb.redis_bus import RedisBus
    from arvel.reverb.server import ReverbServer

    from .conftest import QueueWS

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config, redis_bus=RedisBus(redis=fake_redis, config=config))

    ws = QueueWS()
    await server.start_redis_bridge()
    task = asyncio.create_task(server.handle_connection(ws))
    await ws.push(json.dumps({"event": "pusher:subscribe", "data": {"channel": "orders"}}))
    assert await ws.wait_for("subscription_succeeded")

    broadcaster = RedisBroadcaster(redis=fake_redis)
    await broadcaster.broadcast(["orders"], "OrderShipped", {"order_id": 42})
    assert await ws.wait_for("OrderShipped"), (
        f"Expected Redis-delivered OrderShipped frame; got {ws.sent}"
    )

    await ws.close_input()
    await task


@pytest.mark.asyncio
async def test_reverb_server_excludes_originating_socket(fake_redis: Any) -> None:
    """except_socket_id from the envelope skips the matching local socket."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.broadcasting.drivers.redis import RedisBroadcaster
    from arvel.reverb.redis_bus import RedisBus
    from arvel.reverb.server import ReverbServer

    from .conftest import QueueWS

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config, redis_bus=RedisBus(redis=fake_redis, config=config))

    ws = QueueWS()
    await server.start_redis_bridge()
    task = asyncio.create_task(server.handle_connection(ws))

    socket_id = await ws.wait_handshake()
    await ws.push(json.dumps({"event": "pusher:subscribe", "data": {"channel": "orders"}}))
    assert await ws.wait_for("subscription_succeeded")

    broadcaster = RedisBroadcaster(redis=fake_redis)
    # Excluded frame first, then a sentinel with no exclusion. They traverse the
    # same pump in order, so once the sentinel lands the excluded one was processed.
    await broadcaster.broadcast(
        ["orders"], "ExcludedEvt", {"order_id": 42}, except_socket_id=socket_id
    )
    await broadcaster.broadcast(["orders"], "SentinelEvt", {"order_id": 43})
    assert await ws.wait_for("SentinelEvt")
    assert not any("ExcludedEvt" in m for m in ws.sent)

    await ws.close_input()
    await task
