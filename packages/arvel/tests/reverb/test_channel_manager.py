"""FR-013-025, NFR-013-006 — ChannelManager (in-process pub/sub)."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_subscribe_adds_connection_to_channel() -> None:
    """FR-013-025 AC1: subscribe(channel, connection) registers the connection."""
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    sentinel = object()
    mgr.subscribe("orders", sentinel)
    assert sentinel in mgr.subscribers("orders")


@pytest.mark.asyncio
async def test_unsubscribe_removes_connection() -> None:
    """FR-013-025 AC2: unsubscribe removes the connection."""
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    conn = object()
    mgr.subscribe("orders", conn)
    mgr.unsubscribe("orders", conn)
    assert conn not in mgr.subscribers("orders")


@pytest.mark.asyncio
async def test_publish_fans_out_to_all_subscribers() -> None:
    """FR-013-025 AC3: publish dispatches the event frame to every subscriber on the channel."""
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    received_a: list[str] = []
    received_b: list[str] = []

    class _Conn:
        def __init__(self, bucket: list[str]) -> None:
            self._b: list[str] = bucket

        async def send(self, frame: str) -> None:
            self._b.append(frame)

    a = _Conn(received_a)
    b = _Conn(received_b)
    mgr.subscribe("orders", a)
    mgr.subscribe("orders", b)
    await mgr.publish("orders", "OrderShipped", {"order_id": 42})
    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_publish_skips_except_socket_id() -> None:
    """FR-013-025 AC4: except_socket_id excludes the originating connection."""
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    received_a: list[str] = []
    received_b: list[str] = []

    class _Conn:
        def __init__(self, sid: str, bucket: list[str]) -> None:
            self.socket_id: str = sid
            self._b: list[str] = bucket

        async def send(self, frame: str) -> None:
            self._b.append(frame)

    a = _Conn("1.1", received_a)
    b = _Conn("2.2", received_b)
    mgr.subscribe("orders", a)
    mgr.subscribe("orders", b)
    await mgr.publish("orders", "X", {}, except_socket_id="1.1")
    assert not received_a
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_send_failure_disconnects_connection() -> None:
    """NFR-013-006: slow / failing connection is removed; fan-out continues for others."""
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    received: list[str] = []

    class _BadConn:
        socket_id = "bad"

        async def send(self, frame: str) -> None:
            raise ConnectionError("dead")

    class _GoodConn:
        socket_id = "good"

        async def send(self, frame: str) -> None:
            received.append(frame)

    bad = _BadConn()
    good = _GoodConn()
    mgr.subscribe("orders", bad)
    mgr.subscribe("orders", good)
    await mgr.publish("orders", "X", {})
    assert len(received) == 1
    assert bad not in mgr.subscribers("orders")


@pytest.mark.asyncio
async def test_publish_to_empty_channel_is_noop() -> None:
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    # MUST NOT raise even if no subscribers
    await mgr.publish("no-such-channel", "X", {})


@pytest.mark.asyncio
async def test_concurrent_subscribe_unsubscribe_is_safe() -> None:
    """Stress: many concurrent subscribes don't corrupt the registry."""
    from arvel.reverb.channel_manager import ChannelManager

    mgr = ChannelManager()
    conns = [object() for _ in range(50)]

    async def _sub(c: object) -> None:
        mgr.subscribe("orders", c)

    await asyncio.gather(*(_sub(c) for c in conns))
    assert len(mgr.subscribers("orders")) == 50
