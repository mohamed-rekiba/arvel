"""Broadcasting (doc 11, spec 19) — BroadcastManager + dispatcher integration for ShouldBroadcast,
channels, channel-authorization, to_others/broadcast_when, and the redis driver."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.broadcasting import (
    BroadcastManager,
    Channel,
    InteractsWithSockets,
    LogBroadcaster,
    PresenceChannel,
    PrivateChannel,
    RedisBroadcaster,
    accepts,
    bind_socket_id,
    channels_for,
    event_name,
)
from arvel.events.dispatcher import Dispatcher, ShouldBroadcast
from arvel.kernel.container import Container


class OrderShipped(ShouldBroadcast):
    def broadcast_on(self) -> list[str]:
        return ["orders", "private-user.1"]

    def broadcast_as(self) -> str:
        return "order.shipped"


async def test_manager_records_via_log_driver() -> None:
    manager = BroadcastManager()
    assert manager.default_driver() == "log"
    await manager.broadcast(OrderShipped())
    driver = manager.driver()
    assert isinstance(driver, LogBroadcaster)
    name, channels, _ = driver.sent[0]
    assert name == "order.shipped"
    assert channels == ["orders", "private-user.1"]


async def test_dispatcher_broadcasts_shouldbroadcast_events() -> None:
    container = Container()
    manager = BroadcastManager()
    container.instance("broadcast", manager)
    dispatcher = Dispatcher(container)

    await dispatcher.dispatch(OrderShipped())
    assert len(manager.driver().sent) == 1


def test_channel_and_name_helpers_default() -> None:
    class Plain: ...

    assert channels_for(Plain()) == []
    assert event_name(Plain()) == "Plain"


# --- channels: wire-name prefixes (spec 19 §1) -----------------------------


def test_channel_wire_names_get_pusher_prefixes() -> None:
    assert str(Channel("orders")) == "orders"
    assert str(PrivateChannel("chat.5")) == "private-chat.5"
    assert str(PresenceChannel("room.1")) == "presence-room.1"


class ShipmentUpdated(ShouldBroadcast):
    def broadcast_on(self) -> list[Any]:
        return [PrivateChannel("orders.1")]


async def test_broadcast_on_with_private_channel_sends_on_prefixed_name() -> None:
    manager = BroadcastManager()
    await manager.broadcast(ShipmentUpdated())
    _, channels, _ = manager.driver().sent[0]
    assert channels == ["private-orders.1"]


# --- channel authorization (spec 19 §1) ------------------------------------


async def test_private_channel_authorizes_the_matching_user() -> None:
    manager = BroadcastManager()

    async def only_owner(user: Any, chat_id: str) -> bool:
        return user == f"user-{chat_id}"

    manager.channel("chat.{id}", only_owner)

    assert await manager.authorize("private-chat.5", "user-5") is True
    assert await manager.authorize("private-chat.5", "user-9") is False


async def test_no_matching_pattern_denies() -> None:
    manager = BroadcastManager()
    assert await manager.authorize("private-unregistered.1", "someone") is False


async def test_presence_member_with_no_metadata_is_authorized() -> None:
    # a presence callback returning {} is a valid member with no metadata, not a denial
    manager = BroadcastManager()
    manager.channel("room.{id}", lambda user, room_id: {})
    assert await manager.authorize("presence-room.9", "user-1") == {}


async def test_presence_callback_returning_none_denies() -> None:
    manager = BroadcastManager()
    manager.channel("room.{id}", lambda user, room_id: None)
    assert await manager.authorize("presence-room.9", "user-1") is False


async def test_presence_channel_returns_member_data() -> None:
    manager = BroadcastManager()

    def member_data(user: Any, room_id: str) -> dict[str, Any] | bool:
        if user != "ada":
            return False
        return {"id": user, "room": room_id}

    manager.channel("room.{id}", member_data)

    assert await manager.authorize("presence-room.9", "ada") == {"id": "ada", "room": "9"}
    assert await manager.authorize("presence-room.9", "bob") is False


# --- to_others / broadcast_when (spec 19 §1) -------------------------------


class Pinged(ShouldBroadcast, InteractsWithSockets):
    def broadcast_on(self) -> list[Any]:
        return ["room"]


async def test_to_others_excludes_the_originating_socket() -> None:
    event = Pinged().to_others("socket-A")
    manager = BroadcastManager()
    await manager.broadcast(event)
    payload = {"except_socket_id": event._except_socket_id}
    assert accepts(payload, "socket-A") is False  # the sender's own connection: skipped
    assert accepts(payload, "socket-B") is True  # every other subscriber: delivered


async def test_to_others_reads_the_bound_socket_id_when_not_given_explicitly() -> None:
    bind_socket_id("bound-socket")
    try:
        event = Pinged().to_others()
        assert event._except_socket_id == "bound-socket"
    finally:
        bind_socket_id(None)


async def test_broadcast_when_false_suppresses_the_broadcast() -> None:
    manager = BroadcastManager()
    event = Pinged().broadcast_when(lambda: False)
    await manager.broadcast(event)
    assert manager.driver().sent == []


async def test_broadcast_when_true_still_broadcasts() -> None:
    manager = BroadcastManager()
    event = Pinged().broadcast_when(lambda: True)
    await manager.broadcast(event)
    assert len(manager.driver().sent) == 1


# --- redis broadcaster driver (spec 19 §1, story 06) -----------------------


class _FakeRedisConnection:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


class _FakeApp:
    def __init__(self, redis: Any) -> None:
        self._redis = redis

    def make(self, name: str) -> Any:
        assert name == "redis"
        return self._redis


async def test_redis_driver_publishes_one_message_per_channel() -> None:
    import json

    redis = _FakeRedisConnection()
    broadcaster = RedisBroadcaster(_FakeApp(redis))
    await broadcaster.broadcast(ShipmentUpdated())

    assert len(redis.published) == 1
    channel, body = redis.published[0]
    assert channel == "arvel.broadcasting.private-orders.1"
    decoded = json.loads(body)
    assert decoded["event"] == "ShipmentUpdated"
    assert decoded["except_socket_id"] is None


def test_redis_driver_requires_a_bound_app() -> None:
    with pytest.raises(RuntimeError):
        RedisBroadcaster(None)


async def test_manager_resolves_the_redis_driver_from_config() -> None:
    manager = BroadcastManager(_FakeApp(_FakeRedisConnection()))
    driver = manager.driver("redis")
    assert isinstance(driver, RedisBroadcaster)
