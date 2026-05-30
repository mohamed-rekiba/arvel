"""Integration tests for `TaskiqConnection` against a real Redis broker.

Renamed from `test_taskiq_connection_integration.py` per FR-018-15.
Covers FR-018-09 (URL scheme picks redis broker), FR-018-11 (priority via
queue-name suffix routing on the Redis Taskiq broker), and FR-018-12
(no `result_backend_url` field).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

pytest.importorskip("taskiq_redis", reason="arvel[queue-redis] not installed")

from arvel.queue.config import TaskiqQueueConfig
from arvel.queue.drivers.taskiq import TaskiqConnection
from arvel.queue.envelope import JobEnvelope


class RedisEndpoint(Protocol):
    """Structural type for the ``redis_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int


def _envelope(payload: str = "hello", *, priority: int = 0, delay: int = 0) -> JobEnvelope:
    return JobEnvelope(
        job_class="tests.fake.Job",
        payload={"msg": payload},
        attempts=0,
        priority=priority,
        delay=delay,
    )


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestTaskiqRedisBrokerOps:
    @pytest_asyncio.fixture
    async def driver(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[TaskiqConnection]:
        # FR-018-12: result_backend_url is gone — only broker_url
        config = TaskiqQueueConfig(broker_url=redis_endpoint.url)
        connection = TaskiqConnection(config)
        try:
            yield connection
        finally:
            await connection.close()

    async def test_url_scheme_picks_redis_broker(self, driver: TaskiqConnection) -> None:
        """FR-018-09: redis:// scheme resolves to a taskiq_redis broker class."""
        broker = await driver._get_broker()  # pyright: ignore[reportPrivateUsage]
        # Class qualname must come from taskiq_redis
        assert type(broker).__module__.startswith("taskiq_redis")

    async def test_push_delivers_to_broker(
        self, driver: TaskiqConnection, redis_endpoint: RedisEndpoint
    ) -> None:
        """Envelope at priority=0 lands on the default 'taskiq' queue list."""
        import importlib

        redis_asyncio: Any = importlib.import_module("redis.asyncio")

        envelope = _envelope("kicked")
        await driver.push(envelope)

        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        try:
            raw = await client.blpop(["taskiq"], timeout=3)
            assert raw is not None, "expected the broker to enqueue the envelope"
            _name, payload = raw
            parsed = JobEnvelope.from_json(payload.decode())
            assert parsed.payload == {"msg": "kicked"}
        finally:
            await client.aclose()

    async def test_redis_priority_via_queue_suffix(
        self, driver: TaskiqConnection, redis_endpoint: RedisEndpoint
    ) -> None:
        """FR-018-11 redis branch: priority routed to `<base>:p<N>` queue."""
        import importlib

        redis_asyncio: Any = importlib.import_module("redis.asyncio")

        # priority=7 must land on `taskiq:p7`; priority=3 on `taskiq:p3`
        await driver.push(_envelope("hi-prio", priority=7))
        await driver.push(_envelope("lo-prio", priority=3))

        client: Any = redis_asyncio.Redis(host=redis_endpoint.host, port=redis_endpoint.port, db=0)
        try:
            hi = await client.blpop(["taskiq:p7"], timeout=3)
            lo = await client.blpop(["taskiq:p3"], timeout=3)
            assert hi is not None and lo is not None
            hi_env = JobEnvelope.from_json(hi[1].decode())
            lo_env = JobEnvelope.from_json(lo[1].decode())
            assert hi_env.payload == {"msg": "hi-prio"}
            assert lo_env.payload == {"msg": "lo-prio"}
        finally:
            await client.aclose()
