"""First-class websocket routes (AR-003): ``Router.websocket`` registers a socket handler outside
the HTTP pipeline, and ``broadcast_websocket`` is the ready realtime relay over arvel's own redis
broadcast pub/sub + channel-auth (DR-0076)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from litestar.testing import TestClient

from arvel import Application
from arvel.broadcasting import CHANNEL_PREFIX
from arvel.http import HttpKernel
from arvel.kernel import set_application
from arvel.routing import Router, broadcast_websocket


async def _echo(socket: Any) -> None:
    await socket.accept()
    async for message in socket.iter_data("text"):
        await socket.send_text(f"echo:{message}")


def test_router_registers_a_custom_websocket_route() -> None:
    kernel = HttpKernel()
    router = Router()
    router.websocket("/echo", _echo, name="ws.echo")
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client, client.websocket_connect("/echo") as ws:
        ws.send_text("hi")
        assert ws.receive_text() == "echo:hi"


def test_websocket_route_honors_the_group_prefix() -> None:
    kernel = HttpKernel()
    router = Router()
    with router.group(prefix="/rt"):
        router.websocket("/echo", _echo)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client, client.websocket_connect("/rt/echo") as ws:
        ws.send_text("x")
        assert ws.receive_text() == "echo:x"


class _FakeRedis:
    """A minimal redis facade double: ``subscribe(channel)`` replays whatever was ``seed``-ed to
    the channel (before the socket subscribes), then blocks — so the relay can be exercised without
    a real broker or cross-thread publishing."""

    def __init__(self) -> None:
        self._messages: dict[str, list[str]] = {}

    def seed(self, channel: str, body: str) -> None:
        self._messages.setdefault(channel, []).append(body)

    async def subscribe(self, channel: str) -> Any:
        for body in self._messages.get(channel, []):
            yield body
        await asyncio.Event().wait()  # no further messages; the relay task is cancelled on close


def _relay_kernel(redis: _FakeRedis) -> HttpKernel:
    app = Application()
    app.instance("redis", redis)
    set_application(app)
    kernel = HttpKernel()
    router = Router()
    router.websocket("/ws", broadcast_websocket, name="ws.broadcast")
    router.apply_to(kernel)
    return kernel


def test_broadcast_relay_connect_and_public_subscribe_receives_events() -> None:
    redis = _FakeRedis()
    # a broadcast already on the channel's redis topic (arvel's publish wire format) reaches the socket
    redis.seed(
        f"{CHANNEL_PREFIX}stock.1", json.dumps({"event": "StockChanged", "data": {"qty": 3}})
    )
    kernel = _relay_kernel(redis)
    try:
        with TestClient(kernel.build()) as client, client.websocket_connect("/ws") as ws:
            hello = json.loads(ws.receive_text())
            assert hello["event"] == "connected" and hello["socket_id"]
            ws.send_text(json.dumps({"event": "subscribe", "channel": "stock.1"}))
            frame = json.loads(ws.receive_text())
            assert frame == {"event": "StockChanged", "data": {"qty": 3}}
    finally:
        set_application(None)


def test_broadcast_relay_denies_a_private_channel_without_a_valid_token() -> None:
    redis = _FakeRedis()
    kernel = _relay_kernel(redis)
    try:
        with TestClient(kernel.build()) as client, client.websocket_connect("/ws") as ws:
            json.loads(ws.receive_text())  # connected
            ws.send_text(
                json.dumps({"event": "subscribe", "channel": "private-order.1", "auth": "forged"})
            )
            frame = json.loads(ws.receive_text())
            assert frame == {"event": "subscribe_error", "channel": "private-order.1"}
    finally:
        set_application(None)
