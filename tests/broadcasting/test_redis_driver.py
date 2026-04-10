"""Tests for RedisBroadcaster — Redis pub/sub broadcast driver."""

from __future__ import annotations

import orjson
import pytest

from arvel.broadcasting.channels import Channel, PresenceChannel, PrivateChannel
from arvel.broadcasting.contracts import BroadcastContract
from arvel.broadcasting.drivers.redis_driver import RedisBroadcaster
from arvel.broadcasting.exceptions import BroadcastError


class FakeRedisClient:
    """In-process double that records PUBLISH calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.published: list[tuple[str, bytes]] = []
        self._fail = fail
        self._closed = False

    async def publish(self, channel: str, message: bytes | str) -> int:
        if self._fail:
            raise ConnectionError("Redis unavailable")
        raw = message if isinstance(message, bytes) else message.encode()
        self.published.append((channel, raw))
        return 1

    async def aclose(self) -> None:
        self._closed = True


class TestRedisBroadcaster:
    """Unit tests using a fake Redis client — no real server required."""

    async def test_is_broadcast_contract(self) -> None:
        broadcaster = RedisBroadcaster(client=FakeRedisClient())
        assert isinstance(broadcaster, BroadcastContract)

    async def test_publishes_to_single_channel(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client)

        await broadcaster.broadcast(
            [Channel("news")],
            "article.published",
            {"id": 1, "title": "Hello"},
        )

        assert len(client.published) == 1
        channel, raw = client.published[0]
        assert channel == "news"
        payload = orjson.loads(raw)
        assert payload == {"event": "article.published", "data": {"id": 1, "title": "Hello"}}

    async def test_publishes_to_multiple_channels(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client)

        channels = [Channel("news"), PrivateChannel("orders.42"), PresenceChannel("chat.1")]
        await broadcaster.broadcast(channels, "update", {"v": 1})

        assert len(client.published) == 3
        published_channels = [ch for ch, _ in client.published]
        assert published_channels == ["news", "orders.42", "chat.1"]

    async def test_prefix_prepended_to_channel_name(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client, prefix="app:")

        await broadcaster.broadcast([Channel("news")], "test", {})

        channel, _ = client.published[0]
        assert channel == "app:news"

    async def test_empty_prefix_no_change(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client, prefix="")

        await broadcaster.broadcast([Channel("orders")], "placed", {})

        channel, _ = client.published[0]
        assert channel == "orders"

    async def test_payload_is_valid_json(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client)

        await broadcaster.broadcast([Channel("ch")], "evt", {"nested": {"a": [1, 2, 3]}})

        _, raw = client.published[0]
        payload = orjson.loads(raw)
        assert payload["event"] == "evt"
        assert payload["data"]["nested"]["a"] == [1, 2, 3]

    async def test_empty_data_payload(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client)

        await broadcaster.broadcast([Channel("ch")], "ping", {})

        _, raw = client.published[0]
        payload = orjson.loads(raw)
        assert payload == {"event": "ping", "data": {}}

    async def test_publish_failure_raises_broadcast_error(self) -> None:
        client = FakeRedisClient(fail=True)
        broadcaster = RedisBroadcaster(client=client)

        with pytest.raises(BroadcastError, match="Failed to publish"):
            await broadcaster.broadcast([Channel("news")], "fail", {})

    async def test_publish_failure_includes_channel_and_event(self) -> None:
        client = FakeRedisClient(fail=True)
        broadcaster = RedisBroadcaster(client=client, prefix="app:")

        with pytest.raises(BroadcastError, match=r"fail\.event.*app:news") as exc_info:
            await broadcaster.broadcast([Channel("news")], "fail.event", {})

        assert isinstance(exc_info.value.__cause__, ConnectionError)

    async def test_partial_failure_raises_on_first_bad_channel(self) -> None:
        """If the first channel succeeds but the second fails, error is raised."""

        call_count = 0

        class PartialFailClient:
            async def publish(self, channel: str, message: bytes | str) -> int:
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    raise ConnectionError("second channel fails")
                return 1

            async def aclose(self) -> None:
                pass

        broadcaster = RedisBroadcaster(client=PartialFailClient())

        with pytest.raises(BroadcastError):
            await broadcaster.broadcast([Channel("ok"), Channel("bad")], "test", {})

    async def test_aclose_delegates_to_client(self) -> None:
        client = FakeRedisClient()
        broadcaster = RedisBroadcaster(client=client)

        await broadcaster.aclose()

        assert client._closed is True

    async def test_aclose_tolerates_missing_method(self) -> None:
        class MinimalClient:
            async def publish(self, channel: str, message: bytes | str) -> int:
                return 1

        broadcaster = RedisBroadcaster(client=MinimalClient())  # ty: ignore[invalid-argument-type]
        await broadcaster.aclose()


class TestRedisBroadcasterConfig:
    """Settings integration — verify redis_url and redis_prefix fields."""

    def test_settings_has_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROADCAST_DRIVER", "redis")
        monkeypatch.setenv("BROADCAST_REDIS_URL", "redis://custom:6380/5")
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.driver == "redis"
        assert settings.redis_url == "redis://custom:6380/5"

    def test_settings_default_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BROADCAST_REDIS_URL", raising=False)
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_settings_has_redis_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROADCAST_REDIS_PREFIX", "myapp:")
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.redis_prefix == "myapp:"

    def test_settings_default_redis_prefix_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BROADCAST_REDIS_PREFIX", raising=False)
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.redis_prefix == ""


class TestRedisBroadcasterProvider:
    """Provider wires redis driver when BROADCAST_DRIVER=redis."""

    def test_provider_creates_redis_broadcaster(
        self, monkeypatch: pytest.MonkeyPatch, clean_env: None
    ) -> None:
        monkeypatch.setenv("BROADCAST_DRIVER", "redis")
        monkeypatch.setenv("BROADCAST_REDIS_URL", "redis://localhost:6379/0")

        from arvel.broadcasting.provider import _make_broadcaster

        broadcaster = _make_broadcaster()
        assert isinstance(broadcaster, RedisBroadcaster)

    def test_provider_raises_for_unknown_driver(
        self, monkeypatch: pytest.MonkeyPatch, clean_env: None
    ) -> None:
        monkeypatch.setenv("BROADCAST_DRIVER", "websocket")

        from arvel.broadcasting.provider import _make_broadcaster
        from arvel.foundation.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="websocket"):
            _make_broadcaster()
