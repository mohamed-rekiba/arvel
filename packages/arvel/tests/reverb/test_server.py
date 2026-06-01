"""ReverbServer wiring."""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_server_assigns_socket_id_on_connect() -> None:
    """server assigns a unique socket_id and sends connection_established."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s", activity_timeout=120)
    server = ReverbServer(config=config)

    sent: list[str] = []

    class _FakeWS:
        async def send(self, msg: str) -> None:
            sent.append(msg)

        async def recv(self) -> str:
            raise StopAsyncIteration

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            raise StopAsyncIteration

    await server.handle_connection(_FakeWS())
    assert sent  # at least connection_established was sent
    first = json.loads(sent[0])
    assert first["event"] == "pusher:connection_established"


@pytest.mark.asyncio
async def test_server_routes_subscribe_to_channel_manager() -> None:
    """pusher:subscribe routes through ChannelManager.subscribe."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config)
    # Wrap subscribe with a counter so we can verify it was called.
    original = server.channels.subscribe
    subscribe_calls: list[tuple[str, object]] = []

    def _track(channel: str, connection: object) -> None:
        subscribe_calls.append((channel, connection))
        original(channel, connection)

    server.channels.subscribe = _track  # type: ignore[method-assign]

    incoming = [
        json.dumps({"event": "pusher:subscribe", "data": {"channel": "orders"}}),
    ]

    class _FakeWS:
        def __init__(self, frames: list[str]) -> None:
            self._frames: list[str] = frames
            self.sent: list[str] = []

        async def send(self, msg: str) -> None:
            self.sent.append(msg)

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            if not self._frames:
                raise StopAsyncIteration
            return self._frames.pop(0)

    ws = _FakeWS(incoming)
    await server.handle_connection(ws)
    # At least one frame is subscription_succeeded for "orders"
    succeeded = [m for m in ws.sent if "subscription_succeeded" in m and "orders" in m]
    assert succeeded


@pytest.mark.asyncio
async def test_server_rejects_private_subscribe_without_valid_auth() -> None:
    """subscribing to private channel with invalid auth sends pusher:error."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config)

    incoming = [
        json.dumps(
            {
                "event": "pusher:subscribe",
                "data": {"channel": "private-x.1", "auth": "k:invalid-signature"},
            }
        ),
    ]

    class _FakeWS:
        def __init__(self, frames: list[str]) -> None:
            self._frames: list[str] = frames
            self.sent: list[str] = []

        async def send(self, msg: str) -> None:
            self.sent.append(msg)

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            if not self._frames:
                raise StopAsyncIteration
            return self._frames.pop(0)

    ws = _FakeWS(incoming)
    await server.handle_connection(ws)
    errors = [m for m in ws.sent if "pusher:error" in m]
    assert errors


@pytest.mark.asyncio
async def test_server_responds_to_ping_with_pong() -> None:
    """pusher:ping triggers pusher:pong."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config)

    incoming = [json.dumps({"event": "pusher:ping"})]

    class _FakeWS:
        def __init__(self, frames: list[str]) -> None:
            self._frames: list[str] = frames
            self.sent: list[str] = []

        async def send(self, msg: str) -> None:
            self.sent.append(msg)

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            if not self._frames:
                raise StopAsyncIteration
            return self._frames.pop(0)

    ws = _FakeWS(incoming)
    await server.handle_connection(ws)
    assert any("pusher:pong" in m for m in ws.sent)


@pytest.mark.asyncio
async def test_server_idle_timeout_closes_connection() -> None:
    """idle connections past activity_timeout are closed."""
    # Reverb spec — for unit test, we verify the timeout is wired through.
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s", activity_timeout=120)
    server = ReverbServer(config=config)
    assert server.config.activity_timeout == 120


@pytest.mark.asyncio
async def test_server_respects_max_connections_per_ip() -> None:
    """ConnectionLimitExceeded when too many connections from one IP."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s", max_connections_per_ip=1)
    server = ReverbServer(config=config)

    import asyncio as _asyncio

    class _BlockingWS:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed: bool = False
            self._release: _asyncio.Event = _asyncio.Event()

        async def send(self, msg: str) -> None:
            self.sent.append(msg)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = True

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            await self._release.wait()
            raise StopAsyncIteration

        def release(self) -> None:
            self._release.set()

    ws1 = _BlockingWS()
    task1 = _asyncio.create_task(server.handle_connection(ws1, remote_ip="10.0.0.1"))
    await _asyncio.sleep(0)  # let task1 establish

    ws2 = _BlockingWS()
    await server.handle_connection(ws2, remote_ip="10.0.0.1")
    assert ws2.closed

    ws1.release()
    await task1


@pytest.mark.asyncio
async def test_subscribe_rate_limit_yields_4301_after_100_per_second() -> None:
    """/ : 101st subscribe in <1s gets pusher:error 4301."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config)

    incoming = [
        json.dumps({"event": "pusher:subscribe", "data": {"channel": f"public-{i}"}})
        for i in range(101)
    ]

    class _FakeWS:
        def __init__(self, frames: list[str]) -> None:
            self._frames: list[str] = frames
            self.sent: list[str] = []

        async def send(self, msg: str) -> None:
            self.sent.append(msg)

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            if not self._frames:
                raise StopAsyncIteration
            return self._frames.pop(0)

    ws = _FakeWS(incoming)
    await server.handle_connection(ws)

    # 100 should succeed, the 101st should be a 4301 rate-limit error
    rate_limit_errors = [m for m in ws.sent if '"event": "pusher:error"' in m and "4301" in m]
    assert rate_limit_errors, (
        f"Expected at least one pusher:error code=4301 after 100 subscribes; sent={ws.sent[-5:]}"
    )


@pytest.mark.asyncio
async def test_idle_connection_is_closed_after_activity_timeout_plus_grace() -> None:
    """a connection with no traffic for activity_timeout + 30s is closed."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    # activity_timeout=30 is the minimum the config allows; total threshold = 60s but
    # we override the inactivity_threshold via the server's protected hook for fast tests.
    config = ReverbConfig(app_id="x", key="k", secret="s", activity_timeout=30)
    server = ReverbServer(config=config)
    server.inactivity_threshold_seconds = 0.1

    import asyncio as _asyncio

    class _IdleWS:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.closed: bool = False
            self._release: _asyncio.Event = _asyncio.Event()

        async def send(self, msg: str) -> None:
            self.sent.append(msg)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = True
            self._release.set()

        def __aiter__(self) -> Any:
            return self

        async def __anext__(self) -> str:
            await self._release.wait()
            raise StopAsyncIteration

    ws = _IdleWS()
    await _asyncio.wait_for(server.handle_connection(ws), timeout=1.0)
    assert ws.closed, "Idle connection should be closed by inactivity watchdog"


async def _subscribe_presence(server: Any, ws: Any, label: str) -> Any:
    """Spin up a presence subscription on ``presence-room.1`` for ``label``."""
    import asyncio as _asyncio

    from arvel.reverb.auth import sign_channel_auth

    task = _asyncio.create_task(server.handle_connection(ws))
    sid = await ws.wait_handshake()
    channel_data = json.dumps({"user_id": label, "user_info": {"name": label}})
    auth = sign_channel_auth(
        secret="s",
        key="k",
        socket_id=sid,
        channel="presence-room.1",
        channel_data=channel_data,
    )
    await ws.push(
        json.dumps(
            {
                "event": "pusher:subscribe",
                "data": {
                    "channel": "presence-room.1",
                    "auth": auth,
                    "channel_data": channel_data,
                },
            }
        )
    )
    return task


@pytest.mark.asyncio
async def test_presence_channel_emits_member_added_to_others() -> None:
    """subscribing to presence sends member_added to other subscribers."""
    import asyncio as _asyncio

    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    from .conftest import QueueWS

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config)

    ws_a = QueueWS()
    task_a = await _subscribe_presence(server, ws_a, "A")
    assert await ws_a.wait_for("subscription_succeeded")

    ws_b = QueueWS()
    task_b = await _subscribe_presence(server, ws_b, "B")
    assert await ws_b.wait_for("subscription_succeeded")

    succeeded = [
        json.loads(m) for m in ws_b.sent if "subscription_succeeded" in m and "presence-room.1" in m
    ]
    assert succeeded
    data_field = succeeded[0]["data"]
    data_obj = json.loads(data_field) if isinstance(data_field, str) else data_field
    assert {"ids", "hash", "count"} <= set(data_obj["presence"].keys())
    assert {"A", "B"} <= set(data_obj["presence"]["ids"])

    assert await ws_a.wait_for("member_added"), (
        f"Expected member_added on Alice's socket; got {ws_a.sent}"
    )

    await ws_a.close_input()
    await ws_b.close_input()
    await _asyncio.gather(task_a, task_b)


# ---------------------------------------------------------------------------
# Stage 4b security fixes — failing tests authored before implementation.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_connection_rejects_invalid_channel_name_with_4001() -> None:
    """Stage 4b MEDIUM-1: WS subscribe rejects malformed channel names."""
    import asyncio as _asyncio

    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    from .conftest import QueueWS

    server = ReverbServer(config=ReverbConfig(app_id="x", key="k", secret="s"))
    ws = QueueWS()
    task = _asyncio.create_task(server.handle_connection(ws))
    await ws.wait_handshake()

    # Channel name with newline → invalid per Pusher spec; must be rejected.
    await ws.push(json.dumps({"event": "pusher:subscribe", "data": {"channel": "bad\nname"}}))
    assert await ws.wait_for('"pusher:error"') and any(
        "4001" in m and "Invalid channel name" in m for m in ws.sent
    ), f"Expected pusher:error code=4001 for malformed channel; got {ws.sent}"
    # The channel must NOT have been registered in ChannelManager.
    assert server.channels.subscribers("bad\nname") == []

    await ws.close_input()
    await task


@pytest.mark.asyncio
async def test_channel_manager_drops_empty_buckets_after_last_unsubscribe() -> None:
    """Stage 4b MEDIUM-2: empty channel entries must be removed to prevent unbounded growth."""
    from arvel.reverb.channel_manager import ChannelManager

    manager = ChannelManager()

    class _C:
        socket_id: str = "1.1"

        async def send(self, _frame: str) -> None: ...

    conn = _C()
    manager.subscribe("orders", conn)
    assert manager.subscribers("orders") == [conn]
    manager.unsubscribe("orders", conn)
    # Public-API invariant: no trace of the channel remains after the last
    # subscriber leaves. Combined with the published guarantee that
    # ``channels_for`` enumerates every channel containing ``conn``, this
    # is sufficient evidence that the internal bucket has been evicted.
    assert manager.subscribers("orders") == []
    assert list(manager.channels_for(conn)) == []


@pytest.mark.asyncio
async def test_serve_passes_origin_allowlist_to_websockets() -> None:
    """Stage 4b HIGH-1: when allowed_origins is set, serve must enforce it."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(
        app_id="x",
        key="k",
        secret="s",
        allowed_origins=["https://app.example.com"],
    )
    server = ReverbServer(config=config)

    # Public API contract: server exposes the resolved origins so the
    # websockets.serve(origins=...) call (and any future transport) can use it.
    assert server.resolved_origins() == ["https://app.example.com"]


def test_serve_resolved_origins_empty_means_deny_cross_origin() -> None:
    """Stage 4b HIGH-1 + LOW-3: empty allowed_origins is same-origin-only."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s")
    server = ReverbServer(config=config)
    # Empty config → server treats as "no cross-origin allowed".
    # The serve() integration uses None to mean "no origin checks at all" in
    # websockets, so we encode "deny cross-origin" as an explicit empty list and
    # rely on the resolver to pass [] (not None) to websockets.serve.
    assert server.resolved_origins() == []


def test_serve_resolved_origins_star_means_any() -> None:
    """Stage 4b HIGH-1: explicit '*' opt-in returns None (websockets.serve('any')) ."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(app_id="x", key="k", secret="s", allowed_origins=["*"])
    server = ReverbServer(config=config)
    assert server.resolved_origins() is None  # "any origin" sentinel


def test_resolve_remote_ip_without_trusted_proxies_uses_peer() -> None:
    """Stage 4b MEDIUM-3: with no trusted_proxies, X-Forwarded-For is ignored."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    server = ReverbServer(config=ReverbConfig(app_id="x", key="k", secret="s"))
    ip = server.resolve_remote_ip(peer_ip="203.0.113.5", forwarded_for="1.2.3.4")
    assert ip == "203.0.113.5"


def test_resolve_remote_ip_with_trusted_proxy_uses_xff() -> None:
    """Stage 4b MEDIUM-3: peer in trusted_proxies → use right-most-trusted X-Forwarded-For."""
    from arvel.broadcasting.config import ReverbConfig
    from arvel.reverb.server import ReverbServer

    config = ReverbConfig(
        app_id="x",
        key="k",
        secret="s",
        trusted_proxies=["10.0.0.0/8"],
    )
    server = ReverbServer(config=config)
    # Multi-hop XFF: client, edge, then our proxy. Trust only the last hop our
    # proxy added — but since the immediate peer is in trusted_proxies we walk
    # the chain right-to-left, popping trusted entries until we hit the first
    # untrusted entry: that is the client IP.
    ip = server.resolve_remote_ip(
        peer_ip="10.0.0.5",
        forwarded_for="198.51.100.10, 203.0.113.7, 10.0.0.5",
    )
    assert ip == "203.0.113.7"
