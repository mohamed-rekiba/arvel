"""Real-Redis integration test for ``RedisBus``
The existing ``test_redis_fanout.py`` uses ``fakeredis`` to assert in-process
behaviour. This file boots the real Redis container and verifies the
cross-process fan-out actually traverses Redis pub/sub: two ``RedisBus``
instances on the same channel, one publishes, the other's subscriber
callback fires with the original envelope.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

redis_asyncio = pytest.importorskip("redis.asyncio", reason="arvel[redis] not installed")

from arvel.broadcasting.config import ReverbConfig  # noqa: E402
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
    async def publisher(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisBus]:
        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        bus = RedisBus(redis=client, config=_config())
        try:
            yield bus
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

    async def test_publish_reaches_a_different_subscriber(
        self, publisher: RedisBus, subscriber: RedisBus
    ) -> None:
        received: list[tuple[str, str, dict[str, object]]] = []
        done = asyncio.Event()

        async def on_message(channel: str, event: str, data: dict[str, object]) -> None:
            received.append((channel, event, data))
            done.set()

        await subscriber.subscribe(on_message)
        # Give the SUBSCRIBE round-trip a moment to register before the publish
        # lands; without this the message can hit Redis before the subscriber's
        # pump task has actually subscribed.
        await asyncio.sleep(0.2)

        await publisher.publish("orders", "order.placed", {"id": 7})

        try:
            await asyncio.wait_for(done.wait(), timeout=3.0)
        except TimeoutError:
            pytest.fail("expected the subscriber to observe the published event")

        assert received == [("orders", "order.placed", {"id": 7})]

    async def test_subscriber_filters_own_origin(self, publisher: RedisBus) -> None:
        # Publishing on the same bus must not fan back to its own subscriber
        # callback — the envelope carries an origin token that suppresses
        # the self-loop.
        received: list[tuple[str, str, dict[str, object]]] = []

        async def on_message(channel: str, event: str, data: dict[str, object]) -> None:
            received.append((channel, event, data))

        await publisher.subscribe(on_message)
        await asyncio.sleep(0.2)

        await publisher.publish("orders", "order.placed", {"id": 11})

        # Give pubsub a moment to deliver; if the self-loop fires we'll see it.
        await asyncio.sleep(0.5)
        assert received == []
