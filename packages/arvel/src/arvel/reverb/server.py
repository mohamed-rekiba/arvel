"""ReverbServer — Pusher-protocol WS server."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import secrets
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any, Protocol, cast

from arvel.broadcasting.channels import validate_channel_name
from arvel.broadcasting.config import ReverbConfig
from arvel.broadcasting.exceptions import BroadcastChannelError
from arvel.reverb.auth import verify_channel_auth
from arvel.reverb.channel_manager import ChannelManager
from arvel.reverb.protocol import (
    build_connection_established,
    build_error,
    build_pong,
    build_subscription_succeeded,
)

if TYPE_CHECKING:
    from arvel.reverb.redis_bus import RedisBus

logger = logging.getLogger(__name__)

# Subscribe-storm cap: 100 attempts/sec/socket → pusher:error 4301.
_SUBSCRIBE_RATE_LIMIT = 100
_SUBSCRIBE_WINDOW_SECONDS = 1.0


def _as_str_keyed(d: Any) -> dict[str, object]:
    """Coerce an opaque JSON object into a typed ``dict[str, object]``.

    Parameter is typed ``Any`` because callers feed partially-unknown values
    from ``json.loads`` and from narrowed ``isinstance(x, dict)`` checks,
    which Pyright still treats as ``dict[Unknown, Unknown]``.
    """
    if not isinstance(d, dict):
        return {}
    typed = cast("dict[Any, Any]", d)  # type: ignore[redundant-cast]
    return {str(k): v for k, v in typed.items()}


class _WS(Protocol):
    """Minimum WebSocket surface ReverbServer relies on.

    ``close`` is optional — only required for connections rejected by the
    per-IP limit gate or the inactivity watchdog.
    """

    async def send(self, msg: str) -> None: ...

    def __aiter__(self) -> Any: ...

    async def __anext__(self) -> str: ...


class _Connection:
    """Per-socket state: identity, presence membership, subscribe-rate window."""

    def __init__(self, ws: _WS, socket_id: str) -> None:
        self.ws: _WS = ws
        self.socket_id: str = socket_id
        self.last_activity: float = time.monotonic()
        self._subscribe_window: list[float] = []
        # Presence membership: channel → {"user_id": str, "user_info": dict}.
        self.presence: dict[str, dict[str, object]] = {}

    async def send(self, frame: str) -> None:
        await self.ws.send(frame)

    def mark_activity(self) -> None:
        self.last_activity = time.monotonic()

    def record_subscribe(self) -> bool:
        """Return True if under the per-sec cap; False if it should be rejected."""
        now = time.monotonic()
        cutoff = now - _SUBSCRIBE_WINDOW_SECONDS
        self._subscribe_window = [t for t in self._subscribe_window if t > cutoff]
        if len(self._subscribe_window) >= _SUBSCRIBE_RATE_LIMIT:
            return False
        self._subscribe_window.append(now)
        return True


class ReverbServer:
    """In-process Pusher-protocol WS server.

    The server may optionally bind a :class:`RedisBus` for cross-process
    fan-out. When wired, every envelope received from Redis is fanned out
    to local subscribers via :attr:`channels`.
    """

    def __init__(
        self,
        *,
        config: ReverbConfig,
        redis_bus: RedisBus | None = None,
    ) -> None:
        self.config: ReverbConfig = config
        self.channels: ChannelManager = ChannelManager()
        self._connections_per_ip: dict[str, int] = defaultdict(int)
        self._redis_bus: RedisBus | None = redis_bus
        # Hold strong refs to fire-and-forget tasks so the loop doesn't GC them.
        self._background_tasks: set[asyncio.Task[None]] = set()
        # Watchdog default: activity_timeout + 30s grace.
        # Public so deployments (and tests) can shrink the window without subclassing.
        self.inactivity_threshold_seconds: float = float(config.activity_timeout + 30)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        """Schedule a fire-and-forget coroutine and keep a strong reference."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def resolved_origins(self) -> list[str] | None:
        """HIGH-1 / LOW-3 (Stage 4b): turn ``allowed_origins`` into a serve()-ready value.

        Semantics:
            - ``["*"]`` (explicit opt-in) → ``None`` ("any origin").
            - ``[]`` (default) → ``[]``; ``websockets.serve(origins=[])`` rejects
              every cross-origin handshake, which is the safe default for a WS
              server that sits behind cookie/session auth.
            - otherwise → the configured list, coerced to ``str``.
        """
        origins = [str(o) for o in self.config.allowed_origins]
        if origins == ["*"]:
            return None
        return origins

    def resolve_remote_ip(self, *, peer_ip: str, forwarded_for: str | None) -> str:
        """MEDIUM-3 (Stage 4b): right-most-trusted-hop X-Forwarded-For resolution.

        If the TCP peer is in ``trusted_proxies``, walk the XFF header right-to-left
        and skip every entry that also belongs to a trusted proxy. The first
        untrusted hop is the real client. Without ``trusted_proxies`` configured,
        always return ``peer_ip`` — never trust forwarded headers, since they're
        client-controlled by default.
        """
        trusted = self.config.trusted_proxies
        if not trusted or not forwarded_for or not self._is_trusted_proxy(peer_ip, trusted):
            return peer_ip
        for hop in reversed([h.strip() for h in forwarded_for.split(",") if h.strip()]):
            if not self._is_trusted_proxy(hop, trusted):
                return hop
        return peer_ip

    @staticmethod
    def _is_trusted_proxy(ip: str, trusted: list[str]) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for entry in trusted:
            try:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                elif addr == ipaddress.ip_address(entry):
                    return True
            except ValueError:
                continue
        return False

    async def start_redis_bridge(self) -> None:
        """Subscribe the configured RedisBus and feed envelopes into ChannelManager."""
        if self._redis_bus is None:
            return

        async def _bridge(
            channel: str,
            event: str,
            payload: dict[str, object],
            except_socket_id: str | None,
        ) -> None:
            await self.channels.publish(channel, event, payload, except_socket_id=except_socket_id)

        await self._redis_bus.subscribe(_bridge)

    async def handle_connection(self, ws: _WS, remote_ip: str | None = None) -> None:
        ip = remote_ip or "unknown"
        if self._connections_per_ip[ip] >= self.config.max_connections_per_ip:
            await self._best_effort_close(ws, code=4100, reason="ConnectionLimitExceeded")
            return

        self._connections_per_ip[ip] += 1
        socket_id = self._new_socket_id()
        conn = _Connection(ws, socket_id)
        watchdog = asyncio.create_task(self._inactivity_watchdog(conn))
        try:
            await conn.send(
                build_connection_established(
                    socket_id=socket_id,
                    activity_timeout=self.config.activity_timeout,
                ),
            )
            async for raw in ws:
                conn.mark_activity()
                await self._route(conn, raw)
        finally:
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError, Exception:
                pass
            self._cleanup_connection(conn)
            self._connections_per_ip[ip] -= 1

    def _cleanup_connection(self, conn: _Connection) -> None:
        """Unsubscribe from every channel; emit member_removed for presence channels."""
        for channel in list(self.channels.channels_for(conn)):
            self._unsubscribe(conn, channel)

    def _unsubscribe(self, conn: _Connection, channel: str) -> None:
        """Drop a single subscription. For presence channels, emit member_removed
        once the connection's last membership for that user_id is gone (Pusher dedupes
        members by user_id, so concurrent tabs of the same user only fire once)."""
        self.channels.unsubscribe(channel, conn)
        presence = conn.presence.pop(channel, None)
        if presence is None:
            return
        user_id = str(presence.get("user_id", ""))
        if user_id and not self._user_still_present(channel, user_id):
            self._spawn(
                self.channels.publish(
                    channel,
                    "pusher_internal:member_removed",
                    {"user_id": user_id},
                ),
            )

    def _user_still_present(self, channel: str, user_id: str) -> bool:
        """True if any remaining subscriber on ``channel`` shares ``user_id``."""
        for sub in self.channels.subscribers(channel):
            sub_presence = getattr(sub, "presence", None)
            if not isinstance(sub_presence, dict):
                continue
            member = _as_str_keyed(sub_presence).get(channel)
            if not isinstance(member, dict):
                continue
            if str(_as_str_keyed(member).get("user_id", "")) == user_id:
                return True
        return False

    async def _inactivity_watchdog(self, conn: _Connection) -> None:
        """Close the connection if no traffic for ``inactivity_threshold_seconds``."""
        threshold = self.inactivity_threshold_seconds
        # Poll roughly five times per window — fast enough for tests, cheap in prod.
        poll = max(0.01, threshold / 5)
        while True:
            await asyncio.sleep(poll)
            idle_for = time.monotonic() - conn.last_activity
            if idle_for >= threshold:
                await self._best_effort_close(conn.ws, code=1000, reason="ActivityTimeout")
                return

    @staticmethod
    async def _best_effort_close(ws: _WS, *, code: int, reason: str) -> None:
        close_obj: object = getattr(ws, "close", None)
        if not callable(close_obj):
            return
        close_fn = cast("Callable[..., Awaitable[object]]", close_obj)
        try:
            await close_fn(code=code, reason=reason)
        except Exception:
            logger.debug("reverb_close_failed code=%s", code, exc_info=True)

    async def _route(self, conn: _Connection, raw: str) -> None:
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError:
            await conn.send(build_error(code=4001, message="Invalid JSON frame"))
            return
        if not isinstance(parsed, dict):
            await conn.send(build_error(code=4001, message="Frame must be a JSON object"))
            return
        msg = _as_str_keyed(parsed)
        event: object = msg.get("event")
        data: object = msg.get("data", {})
        if event == "pusher:ping":
            await conn.send(build_pong())
            return
        if event == "pusher:subscribe":
            await self._handle_subscribe(conn, data)
            return
        if event == "pusher:unsubscribe":
            channel = _as_str_keyed(data).get("channel")
            if isinstance(channel, str):
                self._unsubscribe(conn, channel)
            return

    async def _handle_subscribe(self, conn: _Connection, data: object) -> None:
        if not isinstance(data, dict):
            await conn.send(build_error(code=4001, message="Invalid subscribe data"))
            return
        if not conn.record_subscribe():
            await conn.send(build_error(code=4301, message="Subscription rate limited"))
            return

        typed = _as_str_keyed(data)
        channel_raw: object = typed.get("channel")
        if not isinstance(channel_raw, str):
            await conn.send(build_error(code=4001, message="Channel name required"))
            return
        try:
            validate_channel_name(channel_raw)
        except BroadcastChannelError:
            # MEDIUM-1 + LOW-2 (Stage 4b): block the WS-side subscribe and log
            # for observability. The raw channel is repr'd to neutralise control chars.
            logger.warning(
                "reverb_subscribe_rejected reason=invalid_channel socket_id=%s channel=%r",
                conn.socket_id,
                channel_raw,
            )
            await conn.send(build_error(code=4001, message="Invalid channel name"))
            return

        presence_data: dict[str, object] | None = None
        if channel_raw.startswith(("private-", "presence-")):
            auth_raw: object = typed.get("auth")
            cd_raw: object = typed.get("channel_data")
            cd_str: str | None = cd_raw if isinstance(cd_raw, str) else None
            if not isinstance(auth_raw, str) or not verify_channel_auth(
                auth=auth_raw,
                secret=self.config.secret,
                key=self.config.key,
                socket_id=conn.socket_id,
                channel=channel_raw,
                channel_data=cd_str,
            ):
                await conn.send(build_error(code=4009, message="Invalid signature"))
                return
            if channel_raw.startswith("presence-"):
                presence_data = self._parse_channel_data(cd_str) if cd_str else None
                # Presence channels require channel_data carrying user_id; without it
                # the roster is meaningless. Pusher rejects rather than silently
                # downgrading to a plain private subscription.
                if presence_data is None or not str(presence_data.get("user_id", "")):
                    await conn.send(
                        build_error(code=4009, message="Presence channel_data required")
                    )
                    return

        await self._complete_subscribe(conn, channel_raw, presence_data)

    @staticmethod
    def _parse_channel_data(raw: str) -> dict[str, object] | None:
        try:
            parsed = json.loads(raw)
        except TypeError, ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        return _as_str_keyed(parsed)

    async def _complete_subscribe(
        self,
        conn: _Connection,
        channel: str,
        presence_data: dict[str, object] | None,
    ) -> None:
        self.channels.subscribe(channel, conn)
        if presence_data is None or not channel.startswith("presence-"):
            await conn.send(
                build_subscription_succeeded(channel=channel, presence_data=None),
            )
            return

        user_id = str(presence_data.get("user_id", ""))
        user_info_raw: object = presence_data.get("user_info", {})
        user_info: dict[str, object] = (
            _as_str_keyed(user_info_raw) if isinstance(user_info_raw, dict) else {}
        )
        # Was this user_id already on the channel via another connection? Checked
        # before recording our own membership so member_added fires once per user.
        already_present = bool(user_id) and self._user_still_present(channel, user_id)

        # Record member, then fan out: roster to the subscriber, member_added to others.
        conn.presence[channel] = presence_data
        roster = self._build_presence_roster(channel)
        await conn.send(
            build_subscription_succeeded(
                channel=channel,
                presence_data=roster,
            ),
        )
        if user_id and not already_present:
            await self.channels.publish(
                channel,
                "pusher_internal:member_added",
                {"user_id": user_id, "user_info": user_info},
                except_socket_id=conn.socket_id,
            )

    def _build_presence_roster(self, channel: str) -> dict[str, object]:
        ids: list[str] = []
        hash_: dict[str, object] = {}
        for sub in self.channels.subscribers(channel):
            sub_presence_obj: object = getattr(sub, "presence", None)
            if not isinstance(sub_presence_obj, dict):
                continue
            sub_presence = _as_str_keyed(sub_presence_obj)
            data_obj: object = sub_presence.get(channel)
            if not isinstance(data_obj, dict):
                continue
            data = _as_str_keyed(data_obj)
            uid = str(data.get("user_id", ""))
            # Pusher dedupes presence members by user_id — multiple tabs of the
            # same user count once.
            if not uid or uid in hash_:
                continue
            ids.append(uid)
            info: object = data.get("user_info", {})
            hash_[uid] = info if isinstance(info, dict) else {}
        return {"presence": {"ids": ids, "hash": hash_, "count": len(ids)}}

    @staticmethod
    def _new_socket_id() -> str:
        a = secrets.randbelow(10_000_000)
        b = secrets.randbelow(10_000_000)
        return f"{a}.{b}"

    async def serve(self, host: str, port: int) -> None:
        """Bind a real websockets server. Requires the `arvel[broadcasting]` extra."""
        import websockets

        await self.start_redis_bridge()

        async def _handler(websocket: Any, _path: str = "/") -> None:
            peer_ip = str(websocket.remote_address[0])
            xff: str | None = None
            request_headers = getattr(websocket, "request_headers", None)
            if request_headers is not None:
                getter = getattr(request_headers, "get", None)
                if callable(getter):
                    xff_value = getter("X-Forwarded-For")
                    if isinstance(xff_value, str):
                        xff = xff_value
            client_ip = self.resolve_remote_ip(peer_ip=peer_ip, forwarded_for=xff)
            await self.handle_connection(websocket, remote_ip=client_ip)

        # HIGH-1 (Stage 4b): enforce same-origin by default; ``["*"]`` opts into any.
        # ``websockets`` types origins as ``Sequence[Origin | Pattern[str] | None] | None``
        # where ``Origin`` is a string alias; the cast keeps the boundary type-safe.
        origins = cast("Any", self.resolved_origins())
        async with websockets.serve(_handler, host, port, origins=origins):
            await _Forever().wait()


class _Forever:
    async def wait(self) -> None:
        await asyncio.Event().wait()


__all__ = ["ReverbServer"]
