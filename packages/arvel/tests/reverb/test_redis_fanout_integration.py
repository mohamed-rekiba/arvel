"""Real-Redis integration test for the broadcast → Reverb fan-out.

``test_redis_fanout.py`` uses ``fakeredis`` for in-process behaviour. This
file boots the real Redis container and verifies the ADR-013 §4 contract end
to end: a ``RedisBroadcaster`` PUBLISHes under ``arvel.broadcasting.<channel>``
and a ``RedisBus`` PSUBSCRIBEd to ``arvel.broadcasting.*`` observes it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

redis_asyncio = pytest.importorskip("redis.asyncio", reason="arvel[redis] not installed")

from arvel.broadcasting.config import ReverbConfig  # noqa: E402
from arvel.broadcasting.drivers.redis import RedisBroadcaster  # noqa: E402
from arvel.reverb.redis_bus import RedisBus  # noqa: E402


class RedisEndpoint(Protocol):
    """Structural type for the ``redis_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int


def _config() -> ReverbConfig:
    return ReverbConfig(app_id="test", key="key", secret="secret")


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestReverbRedisBusFanout:
    @pytest_asyncio.fixture
    async def publisher(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisBroadcaster]:
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        try:
            yield RedisBroadcaster(redis=client)
        finally:
            await client.aclose()

    @pytest_asyncio.fixture
    async def subscriber(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisBus]:
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        bus = RedisBus(redis=client, config=_config())
        try:
            yield bus
        finally:
            await client.aclose()

    async def test_broadcast_reaches_a_subscriber(
        self, publisher: RedisBroadcaster, subscriber: RedisBus
    ) -> None:
        received: list[tuple[str, str, dict[str, object], str | None]] = []
        done = asyncio.Event()

        async def on_message(
            channel: str, event: str, data: dict[str, object], except_socket_id: str | None
        ) -> None:
            received.append((channel, event, data, except_socket_id))
            done.set()

        await subscriber.subscribe(on_message)
        # Let the PSUBSCRIBE round-trip register before the publish lands.
        await asyncio.sleep(0.2)

        await publisher.broadcast(["orders"], "order.placed", {"id": 7}, except_socket_id="9.9")

        try:
            await asyncio.wait_for(done.wait(), timeout=3.0)
        except TimeoutError:
            pytest.fail("expected the subscriber to observe the published event")

        assert received == [("orders", "order.placed", {"id": 7}, "9.9")]
