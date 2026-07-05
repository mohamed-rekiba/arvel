"""arvel.cache.redis — the direct Redis facade (RedisConnection/RedisPipeline/RedisManager).

Driven against a fake ``redis.asyncio`` client so the whole store slice runs without a broker.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from arvel.cache.redis import RedisConnection, RedisManager, RedisSettings
from arvel.support.manager import MissingExtraError


class _FakePipe:
    def __init__(self) -> None:
        self.cmds: list[tuple[str, tuple[Any, ...]]] = []

    def execute_command(self, name: str, *args: Any) -> None:
        self.cmds.append((name, args))

    async def execute(self) -> list[Any]:
        return [name for name, _ in self.cmds]


class _FakePubSub:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self._messages = messages
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def listen(self):  # noqa: ANN202
        for message in self._messages:
            yield message

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed.append(channel)

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self) -> None:
        self.commands: list[tuple[str, tuple[Any, ...]]] = []
        self.transaction: bool | None = None
        self.closed = False
        self.pubsub_obj = _FakePubSub(
            [
                {"type": "subscribe", "data": 1},  # non-message: skipped
                {"type": "message", "data": b"bytes-payload"},  # decoded
                {"type": "message", "data": "str-payload"},  # passed through
            ]
        )

    async def execute_command(self, name: str, *args: Any) -> Any:
        self.commands.append((name, args))
        return ("RESULT", name, args)

    def pipeline(self, transaction: bool = False) -> _FakePipe:
        self.transaction = transaction
        return _FakePipe()

    async def publish(self, channel: str, message: Any) -> int:
        return 3

    def pubsub(self) -> _FakePubSub:
        return self.pubsub_obj

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        return ("EVAL", script, numkeys, args)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "from_url", lambda url: fake)
    return fake


async def test_command_forwards_to_client(fake_redis: _FakeRedis) -> None:
    conn = RedisConnection("redis://x")
    result = await conn.command("SET", "k", "v")
    assert result == ("RESULT", "SET", ("k", "v"))
    assert fake_redis.commands == [("SET", ("k", "v"))]


async def test_pipeline_batches_and_executes(fake_redis: _FakeRedis) -> None:
    conn = RedisConnection("redis://x")
    async with conn.pipeline(transaction=True) as pipe:
        pipe.command("SET", "a", 1).command("SET", "b", 2)
        results = await pipe.execute()
    assert results == ["SET", "SET"]
    assert fake_redis.transaction is True


async def test_publish_returns_subscriber_count(fake_redis: _FakeRedis) -> None:
    conn = RedisConnection("redis://x")
    assert await conn.publish("chan", "hi") == 3


async def test_subscribe_decodes_and_filters(fake_redis: _FakeRedis) -> None:
    conn = RedisConnection("redis://x")
    received = [msg async for msg in conn.subscribe("chan")]
    assert received == ["bytes-payload", "str-payload"]  # subscribe frame skipped
    assert fake_redis.pubsub_obj.unsubscribed == ["chan"]
    assert fake_redis.pubsub_obj.closed is True


async def test_eval_passes_key_count(fake_redis: _FakeRedis) -> None:
    conn = RedisConnection("redis://x")
    result = await conn.eval("return 1", keys=["k1", "k2"], args=["a"])
    assert result == ("EVAL", "return 1", 2, ("k1", "k2", "a"))
    # defaults: no keys/args
    assert await conn.eval("return 1") == ("EVAL", "return 1", 0, ())


async def test_close_is_idempotent(fake_redis: _FakeRedis) -> None:
    conn = RedisConnection("redis://x")
    await conn.close()  # client never connected -> no-op
    await conn.command("PING")  # forces connect
    await conn.close()
    assert fake_redis.closed is True


def test_connect_without_redis_extra_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "redis.asyncio", None)
    conn = RedisConnection("redis://x")
    with pytest.raises(MissingExtraError):
        conn._connect()  # pyright: ignore[reportPrivateUsage]


# --- RedisManager ---------------------------------------------------------
class _AppWithConfig:
    def __init__(self, redis_cfg: dict[str, Any]) -> None:
        self._cfg = redis_cfg

    def config(self, key: str) -> dict[str, Any]:
        assert key == "redis"
        return self._cfg


def test_manager_resolves_default_and_named_connections() -> None:
    app = _AppWithConfig(
        {"url": "redis://default", "connections": {"cache": {"url": "redis://cache"}}}
    )
    mgr = RedisManager(app)
    default = mgr.connection()
    assert mgr.connection("default") is default  # cached
    named = mgr.connection("cache")
    assert named is not default
    assert mgr.connection("cache") is named


def test_manager_named_connection_without_url_falls_back_to_default_url() -> None:
    app = _AppWithConfig({"url": "redis://default", "connections": {"bare": {}}})
    mgr = RedisManager(app)
    assert mgr.connection("bare")._url == "redis://default"  # pyright: ignore[reportPrivateUsage]


def test_manager_unknown_connection_raises() -> None:
    mgr = RedisManager()
    with pytest.raises(KeyError):
        mgr.connection("nope")


async def test_manager_close_all_and_getattr_forwarding(fake_redis: _FakeRedis) -> None:
    mgr = RedisManager()
    # __getattr__ forwards public attrs to the default connection
    assert await mgr.command("PING") == ("RESULT", "PING", ())
    await mgr.close_all()
    assert fake_redis.closed is True
    with pytest.raises(AttributeError):
        _ = mgr._private_thing  # underscore attrs are not forwarded


def test_settings_defaults() -> None:
    settings = RedisSettings()
    assert settings.url.startswith("redis://")
    assert settings.connections == {}
