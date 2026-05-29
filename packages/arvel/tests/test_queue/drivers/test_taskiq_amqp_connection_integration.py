"""Integration tests for `TaskiqConnection` against a real RabbitMQ broker.

New file per FR-018-16. Covers FR-018-09 (URL scheme picks amqp broker),
FR-018-11 amqp branch (native priority via max_priority=9 on queue
declaration), and FR-018-14 (rabbitmq_endpoint fixture).
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from typing import Any, Protocol

import pytest
import pytest_asyncio

pytest.importorskip("taskiq_aio_pika", reason="arvel[queue-amqp] not installed")
pytest.importorskip("aio_pika", reason="aio_pika required for raw consumer verification")

from arvel.queue.config import TaskiqQueueConfig
from arvel.queue.drivers.taskiq import TaskiqConnection
from arvel.queue.envelope import JobEnvelope


class RabbitmqEndpoint(Protocol):
    """Structural type for the ``rabbitmq_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int
    management_url: str


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
class TestTaskiqAmqpBrokerOps:
    @pytest_asyncio.fixture
    async def driver(self, rabbitmq_endpoint: RabbitmqEndpoint) -> AsyncIterator[TaskiqConnection]:
        config = TaskiqQueueConfig(broker_url=rabbitmq_endpoint.url)
        connection = TaskiqConnection(config)
        try:
            yield connection
        finally:
            await connection.close()

    async def test_url_scheme_picks_amqp_broker(self, driver: TaskiqConnection) -> None:
        """FR-018-09: amqp:// scheme resolves to a taskiq_aio_pika broker class."""
        broker = await driver._get_broker()  # pyright: ignore[reportPrivateUsage]
        assert type(broker).__module__.startswith("taskiq_aio_pika")

    async def test_push_delivers_envelope(
        self, driver: TaskiqConnection, rabbitmq_endpoint: RabbitmqEndpoint
    ) -> None:
        """Envelope arrives on the AMQP queue, decodable as JSON."""
        aio_pika: Any = importlib.import_module("aio_pika")
        envelope = _envelope("kicked-via-amqp")
        await driver.push(envelope)

        conn = await aio_pika.connect_robust(rabbitmq_endpoint.url)
        try:
            channel = await conn.channel()
            queue = await channel.declare_queue("taskiq", durable=True, passive=True)
            # Pull one message
            iter_q = queue.iterator(timeout=5)
            async with iter_q:
                async for message in iter_q:
                    async with message.process():
                        parsed = JobEnvelope.from_json(message.body.decode())
                        assert parsed.payload == {"msg": "kicked-via-amqp"}
                        break
        finally:
            await conn.close()

    async def test_amqp_native_priority(
        self, driver: TaskiqConnection, rabbitmq_endpoint: RabbitmqEndpoint
    ) -> None:
        """FR-018-11 amqp: max-priority=9 queue; consumers see priority order."""
        aio_pika: Any = importlib.import_module("aio_pika")
        # Push lo before hi so FIFO would deliver lo first; native priority must invert this
        await driver.push(_envelope("lo-prio", priority=2))
        await driver.push(_envelope("hi-prio", priority=8))

        conn = await aio_pika.connect_robust(rabbitmq_endpoint.url)
        try:
            channel = await conn.channel()
            queue = await channel.declare_queue("taskiq", durable=True, passive=True)
            received: list[str] = []
            iter_q = queue.iterator(timeout=5)
            async with iter_q:
                async for message in iter_q:
                    async with message.process():
                        parsed = JobEnvelope.from_json(message.body.decode())
                        received.append(parsed.payload["msg"])
                        if len(received) == 2:
                            break
            assert received == ["hi-prio", "lo-prio"]
        finally:
            await conn.close()
