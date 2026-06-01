"""Real-Redis integration tests for ``RedisConnection``
Before this file the ``RedisConnection`` queue driver had zero tests; the
only coverage was the in-process ``SyncConnection`` and a SQLite-backed
``DatabaseConnection``. Booting a real Redis container is the only way
to assert the RPUSH/BLPOP wire path that the driver actually runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import pytest
import pytest_asyncio
from pydantic import SecretStr

pytest.importorskip("redis.asyncio", reason="arvel[queue] not installed")

from arvel.queue.config import RedisQueueConfig
from arvel.queue.drivers.redis import RedisConnection
from arvel.queue.envelope import JobEnvelope


class RedisEndpoint(Protocol):
    """Structural type for the ``redis_endpoint`` fixture (see emulators/fixtures.py)."""

    url: str
    host: str
    port: int


def _envelope(payload: str = "hello") -> JobEnvelope:
    return JobEnvelope(
        job_class="tests.fake.Job",
        payload={"msg": payload},
        attempts=0,
    )


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestRedisConnectionOps:
    @pytest_asyncio.fixture
    async def driver(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisConnection]:
        # Unique queue_key per test instance keeps the session-scoped
        # container free of cross-test interference.
        config = RedisQueueConfig(
            host=redis_endpoint.host,
            port=redis_endpoint.port,
            db=0,
            password=SecretStr(""),
            queue_key=f"arvel_q_int_{id(self)}",
        )
        connection = RedisConnection(config)
        try:
            await connection.clear("default")
            yield connection
        finally:
            await connection.clear("default")
            await connection.close()

    async def test_push_pop_roundtrip(self, driver: RedisConnection) -> None:
        await driver.push(_envelope("first"))
        popped = await driver.pop_blocking(timeout=2.0)
        assert popped is not None
        assert popped.payload == {"msg": "first"}

    async def test_size_reflects_pushes(self, driver: RedisConnection) -> None:
        assert await driver.size() == 0
        await driver.push(_envelope("a"))
        await driver.push(_envelope("b"))
        assert await driver.size() == 2

    async def test_pop_returns_none_on_timeout(self, driver: RedisConnection) -> None:
        # Empty queue + short timeout exercises BLPOP's timeout path.
        assert await driver.pop_blocking(timeout=1.0) is None

    async def test_clear_empties_queue(self, driver: RedisConnection) -> None:
        await driver.push(_envelope("x"))
        await driver.push(_envelope("y"))
        await driver.clear("default")
        assert await driver.size() == 0

    async def test_fifo_within_same_priority(self, driver: RedisConnection) -> None:
        """Within the same priority, push order is preserved on pop."""
        for i in range(3):
            await driver.push(_envelope(f"msg-{i}"))
        for i in range(3):
            popped = await driver.pop_blocking(timeout=2.0)
            assert popped is not None
            assert popped.payload == {"msg": f"msg-{i}"}


def _envelope_dp(payload: str, *, priority: int = 0, delay: int = 0) -> JobEnvelope:
    return JobEnvelope(
        job_class="tests.fake.Job",
        payload={"msg": payload},
        attempts=0,
        priority=priority,
        delay=delay,
    )


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestRedisConnectionDelayPriority:
    """+ : redis-direct delay, priority, no double-dispatch."""

    @pytest_asyncio.fixture
    async def driver(self, redis_endpoint: RedisEndpoint) -> AsyncIterator[RedisConnection]:
        config = RedisQueueConfig(
            host=redis_endpoint.host,
            port=redis_endpoint.port,
            db=0,
            password=SecretStr(""),
            queue_key=f"arvel_q_dp_{id(self)}",
        )
        connection = RedisConnection(config)
        try:
            await connection.clear("default")
            yield connection
        finally:
            await connection.clear("default")
            await connection.close()

    async def test_delayed_jobs_not_popped_early(self, driver: RedisConnection) -> None:
        """delay=3600 envelope is not popped within 1 s timeout."""
        await driver.push(_envelope_dp("delayed", delay=3600))
        popped = await driver.pop_blocking(timeout=1.0)
        assert popped is None

    async def test_priority_pop_order(self, driver: RedisConnection) -> None:
        """higher priority pops first within the ready set."""
        await driver.push(_envelope_dp("p0"))
        await driver.push(_envelope_dp("p7", priority=7))
        await driver.push(_envelope_dp("p3", priority=3))

        first = await driver.pop_blocking(timeout=2.0)
        second = await driver.pop_blocking(timeout=2.0)
        third = await driver.pop_blocking(timeout=2.0)
        assert first is not None and second is not None and third is not None
        assert first.payload["msg"] == "p7"
        assert second.payload["msg"] == "p3"
        assert third.payload["msg"] == "p0"

    async def test_no_double_dispatch_under_contention(
        self, driver: RedisConnection, redis_endpoint: RedisEndpoint
    ) -> None:
        """10 concurrent pops over 100 pushes yields 100 distinct receives."""
        import asyncio

        # Use a SEPARATE driver per worker to mimic real worker processes
        config_template = RedisQueueConfig(
            host=redis_endpoint.host,
            port=redis_endpoint.port,
            db=0,
            password=SecretStr(""),
            queue_key=f"arvel_q_contention_{id(self)}",
        )
        producer = RedisConnection(config_template)
        try:
            await producer.clear("default")
            for i in range(100):
                await producer.push(_envelope_dp(f"job-{i}"))

            async def worker_pop() -> list[JobEnvelope]:
                w = RedisConnection(config_template)
                collected: list[JobEnvelope] = []
                try:
                    while True:
                        env = await w.pop_blocking(timeout=1.0)
                        if env is None:
                            return collected
                        collected.append(env)
                finally:
                    await w.close()

            results = await asyncio.gather(*[worker_pop() for _ in range(10)])
            all_msgs = [env.payload["msg"] for batch in results for env in batch]
            assert len(all_msgs) == 100, f"expected 100 distinct envelopes, got {len(all_msgs)}"
            assert len(set(all_msgs)) == 100, "double-dispatch detected"
        finally:
            await producer.close()
