"""Real-Redis integration tests for ``RedisBroadcaster`` — FR-013-004.

Before this file the broadcaster's Redis path was only covered by an
``AsyncMock`` redis client. This boots the real Redis container, opens a
``SUBSCRIBE`` listener, runs ``RedisBroadcaster.broadcast(...)``, and
asserts the published envelope is the exact JSON shape contracted by the
driver (``arvel.broadcasting.<channel>`` topic + ``{event, data,
except_socket_id}`` payload).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

redis_asyncio = pytest.importorskip("redis.asyncio", reason="arvel[redis] not installed")

from arvel.broadcasting.drivers.redis import RedisBroadcaster  # noqa: E402


class RedisEndpoint(Protocol):
    """Structural type for the ``redis_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestRedisBroadcasterOps:
    @pytest_asyncio.fixture
    async def client(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[Any]:
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        try:
            yield client
        finally:
            await client.aclose()

    async def test_broadcast_publishes_to_prefixed_channel(self, client: Any) -> None:
        broadcaster = RedisBroadcaster(redis=client)

        pubsub: Any = client.pubsub()
        await pubsub.subscribe("arvel.broadcasting.chat-42")
        # Drain the subscribe-ack message so the next read is the publish.
        await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

        await broadcaster.broadcast(
            ["chat-42"],
            "message.posted",
            {"author": "alice", "body": "hi"},
            except_socket_id="sock-1",
        )

        # Real Redis fans out asynchronously; allow a few hundred ms.
        deadline = asyncio.get_event_loop().time() + 2.0
        msg: Any = None
        while asyncio.get_event_loop().time() < deadline:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg is not None:
                break
        assert msg is not None, "expected RedisBroadcaster to publish on the channel"

        body = json.loads(msg["data"])
        assert body == {
            "event": "message.posted",
            "data": {"author": "alice", "body": "hi"},
            "except_socket_id": "sock-1",
        }
        await pubsub.unsubscribe("arvel.broadcasting.chat-42")
        await pubsub.aclose()

    async def test_broadcast_fans_out_to_every_channel(self, client: Any) -> None:
        broadcaster = RedisBroadcaster(redis=client)

        pubsub: Any = client.pubsub()
        await pubsub.subscribe(
            "arvel.broadcasting.room.1",
            "arvel.broadcasting.room.2",
        )
        # Drain subscribe-acks.
        for _ in range(2):
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

        await broadcaster.broadcast(
            ["room.1", "room.2"],
            "tick",
            {"n": 1},
        )

        received: list[str] = []
        deadline = asyncio.get_event_loop().time() + 2.0
        while len(received) < 2 and asyncio.get_event_loop().time() < deadline:
            msg: Any = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg is not None:
                received.append(msg["channel"].decode())
        assert sorted(received) == [
            "arvel.broadcasting.room.1",
            "arvel.broadcasting.room.2",
        ]
        await pubsub.unsubscribe()
        await pubsub.aclose()
