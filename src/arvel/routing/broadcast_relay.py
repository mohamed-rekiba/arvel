"""arvel.routing.broadcast_relay — the first-class realtime broadcast websocket transport.

arvel ships the publish half (`ShouldBroadcast` → redis) and the channel-authorization half
(`POST /broadcasting/auth`, HMAC-signed) of broadcasting. ``broadcast_websocket`` is the third
half: a ready websocket handler that fans arvel's own redis pub/sub out to browser clients, so an
app enables realtime with one line — ``Route.websocket("/ws", broadcast_websocket)`` — instead of
hand-rolling an ASGI relay.

Lives in **routing** (the top layer) because it needs BOTH ``verify_channel_auth`` (routing's own
``broadcasting_auth``) and ``arvel.broadcasting``'s wire helpers (``accepts`` / ``CHANNEL_PREFIX``),
and broadcasting sits well below routing in the module DAG (G1) — so routing composes both without
either importing the other.

Wire protocol (a subset of the Pusher client protocol, transport-agnostic):
- on connect the server sends ``{"event": "connected", "socket_id": "<id>"}``;
- the client subscribes with ``{"event": "subscribe", "channel": "<name>", "auth": "<token>"}``
  (``auth`` required for a ``private-``/``presence-`` channel — the token minted by
  ``/broadcasting/auth``); a bad token gets ``{"event": "subscribe_error", "channel": …}``;
- each broadcast on a subscribed channel arrives as ``{"event": …, "data": …}``, honoring the
  event's ``to_others()`` echo-suppression against this connection's ``socket_id``.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any, cast


def _parse_object(raw: str | bytes) -> dict[str, Any] | None:
    """Parse a JSON text frame into a dict, or ``None`` for malformed / non-object input."""
    try:
        parsed: Any = json.loads(raw)
    except ValueError:
        return None
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else None


async def broadcast_websocket(socket: Any) -> None:
    """Fan arvel's redis broadcast pub/sub out to one browser websocket client (see module docs).

    Reuses arvel's own primitives — ``verify_channel_auth`` (never re-deriving the HMAC),
    ``accepts`` (the ``to_others()`` rule), and the ``CHANNEL_PREFIX`` wire contract — so a future
    signing/format change can't drift this out of sync."""
    from arvel.broadcasting import CHANNEL_PREFIX, accepts
    from arvel.kernel import app
    from arvel.routing.broadcasting_auth import verify_channel_auth

    await socket.accept()
    socket_id = secrets.token_urlsafe(16)
    # every outgoing frame funnels through one queue + one writer task, so concurrent per-channel
    # relay tasks never race each other calling send() directly.
    outbox: asyncio.Queue[str] = asyncio.Queue()
    outbox.put_nowait(json.dumps({"event": "connected", "socket_id": socket_id}))
    subscriptions: dict[str, asyncio.Task[None]] = {}

    async def relay_channel(channel: str) -> None:
        try:
            redis = app().make("redis")
            async for raw in redis.subscribe(f"{CHANNEL_PREFIX}{channel}"):
                envelope = _parse_object(raw)
                if envelope is not None and accepts(envelope, socket_id):
                    await outbox.put(
                        json.dumps({"event": envelope.get("event"), "data": envelope.get("data")})
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            # a relay task must not die silently (the client would still believe it's subscribed) —
            # log it and tell the client the channel dropped, so it can resubscribe.
            from arvel.kernel.logging import LogManager

            LogManager().channel("broadcasting").warning(
                "broadcast_relay_channel_failed", channel=channel, exc_info=True
            )
            outbox.put_nowait(json.dumps({"event": "subscribe_error", "channel": channel}))

    def subscribe(text: str) -> None:
        payload = _parse_object(text)
        if payload is None or payload.get("event") != "subscribe":
            return
        channel = str(payload.get("channel") or "")
        if not channel or channel in subscriptions:
            return
        # private-/presence- channels require a token arvel actually minted; public channels are open
        if channel.startswith(("private-", "presence-")) and not verify_channel_auth(
            channel, socket_id, str(payload.get("auth") or "")
        ):
            outbox.put_nowait(json.dumps({"event": "subscribe_error", "channel": channel}))
            return
        subscriptions[channel] = asyncio.create_task(relay_channel(channel))

    async def drain() -> None:
        while True:
            await socket.send_text(await outbox.get())

    writer = asyncio.create_task(drain())
    try:
        async for text in socket.iter_data("text"):
            if isinstance(text, str) and text:
                subscribe(text)
    finally:
        writer.cancel()
        for task in subscriptions.values():
            task.cancel()
        # gather with return_exceptions so a task that already died with a real error (e.g. a redis
        # drop) doesn't re-raise out of teardown — cancellation + any residual error are absorbed.
        await asyncio.gather(*subscriptions.values(), writer, return_exceptions=True)


__all__ = ["broadcast_websocket"]
