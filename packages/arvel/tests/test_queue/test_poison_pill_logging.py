"""Poison-pill envelope audit logging.

When a queue driver pops a payload that fails ``JobEnvelope.from_json``,
the worker swallows the envelope (returns None) so the loop stays alive,
but it MUST emit a structured ``queue.envelope.malformed`` log so
operators can spot recurring corruption.

These are pure unit tests: no real Redis / DB / broker is involved.
"""

from __future__ import annotations

from typing import Any, cast

import pytest


class TestRedisDriverPoisonPill:
    """RedisConnection.pop_blocking — malformed envelope → warning + None."""

    @pytest.mark.asyncio
    async def test_logs_warning_and_returns_none(self) -> None:
        from arvel.queue.config import RedisQueueConfig
        from arvel.queue.drivers.redis import RedisConnection, RedisQueueConn
        from arvel.testing.observability import FakeObservability

        cfg = RedisQueueConfig()
        conn = RedisConnection(cfg)

        class _FakeRedis:
            async def script_load(self, _script: str) -> str:
                return "fakesha"

            async def evalsha(self, *_a: Any, **_kw: Any) -> bytes:
                return b"not json at all"

        conn._redis = cast("RedisQueueConn", _FakeRedis())  # pyright: ignore[reportPrivateUsage]

        with FakeObservability() as obs:
            result = await conn.pop_blocking(queue="emails", timeout=0.1)

        assert result is None
        malformed_records = [r for r in obs.log_records if r.body == "queue.envelope.malformed"]
        assert len(malformed_records) == 1
        record = malformed_records[0]
        assert record.attributes.get("driver") == "redis"
        assert record.attributes.get("queue") == "emails"
        assert record.attributes.get("exception_type") in {"ValueError", "TypeError"}


class TestDatabaseDriverPoisonPill:
    """DatabaseConnection.pop_blocking — malformed envelope → warning + None."""

    @pytest.mark.asyncio
    async def test_logs_warning_and_returns_none(self) -> None:
        from arvel.queue.drivers.database import DatabaseConnection, JobRow
        from arvel.testing.observability import FakeObservability
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as bind:
                await bind.run_sync(JobRow.metadata.create_all)

            sm = async_sessionmaker(engine, expire_on_commit=False)
            conn = DatabaseConnection.__new__(DatabaseConnection)
            conn._session_factory = sm  # pyright: ignore[reportPrivateUsage]

            import time

            now = int(time.time())
            async with sm() as session, session.begin():
                session.add(
                    JobRow(
                        queue="emails",
                        payload="this isn't json",
                        attempts=0,
                        available_at=now,
                        created_at=now,
                        priority=0,
                    )
                )
            with FakeObservability() as obs:
                result = await conn.pop_blocking(queue="emails", timeout=0.1)
        finally:
            await engine.dispose()

        assert result is None
        malformed_records = [r for r in obs.log_records if r.body == "queue.envelope.malformed"]
        assert len(malformed_records) == 1
        record = malformed_records[0]
        assert record.attributes.get("driver") == "database"
        assert record.attributes.get("queue") == "emails"


class TestTaskiqDriverPoisonPill:
    """TaskiqConnection.pop_blocking — malformed envelope → warning + None."""

    @pytest.mark.asyncio
    async def test_logs_warning_and_returns_none(self) -> None:
        from arvel.queue.config import TaskiqQueueConfig
        from arvel.queue.drivers.taskiq import TaskiqConnection
        from arvel.testing.observability import FakeObservability

        cfg = TaskiqQueueConfig(broker_url="redis://localhost:6379/0")
        driver = TaskiqConnection(cfg)

        class _FakeMessage:
            data = b"definitely not json"

        class _FakeBroker:
            async def startup(self) -> None:
                return None

            async def listen(self) -> Any:
                return _FakeMessage()

            async def kick(self, message: object) -> None:
                return None

            async def shutdown(self) -> None:
                return None

        driver._broker = _FakeBroker()  # pyright: ignore[reportPrivateUsage]
        driver._started = True  # pyright: ignore[reportPrivateUsage]

        with FakeObservability() as obs:
            result = await driver.pop_blocking(queue="emails", timeout=0.1)

        assert result is None
        malformed_records = [r for r in obs.log_records if r.body == "queue.envelope.malformed"]
        assert len(malformed_records) == 1
        record = malformed_records[0]
        assert record.attributes.get("driver") == "taskiq"
        assert record.attributes.get("queue") == "emails"
