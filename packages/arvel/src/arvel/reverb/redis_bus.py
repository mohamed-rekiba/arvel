"""RedisBus — cross-process fan-out for Reverb.

Per ADR-013 §4: ``RedisBroadcaster`` PUBLISHes one message per channel under
``arvel.broadcasting.<channel>``; every Reverb process PSUBSCRIBEs to
``arvel.broadcasting.*`` and forwards each matching message to its locally
connected sockets. This bus is the subscribe half — the publish half is
``arvel.broadcasting.drivers.redis.RedisBroadcaster``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from arvel.broadcasting.config import ReverbConfig

# Must match RedisBroadcaster._CHANNEL_PREFIX — the two are a publish/subscribe pair.
_CHANNEL_PREFIX = "arvel.broadcasting."
_PATTERN = f"{_CHANNEL_PREFIX}*"

#: (channel, event, data, except_socket_id) — the originating socket is excluded
#: from fan-out so the publisher's own client doesn't get an echo.
OnMessage = Callable[[str, str, dict[str, object], "str | None"], Awaitable[None]]


class _AsyncPubSub(Protocol):
    async def psubscribe(self, *patterns: str) -> None: ...

    async def get_message(
        self, *, ignore_subscribe_messages: bool = True, timeout: float | None = None
    ) -> Any: ...


class AsyncRedis(Protocol):
    """Subset of ``redis.asyncio.Redis`` the bus needs — just ``pubsub()``."""

    def pubsub(self) -> _AsyncPubSub: ...


class RedisBus:
    """Subscribe side of the cross-process fan-out: PSUBSCRIBE ``arvel.broadcasting.*``."""

    def __init__(self, *, redis: AsyncRedis, config: ReverbConfig) -> None:
        self._redis = redis
        self._config: ReverbConfig = config
        self._tasks: list[asyncio.Task[None]] = []

    async def subscribe(self, on_message: OnMessage) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(_PATTERN)

        async def _pump() -> None:
            while True:
                msg: object = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if msg is None:
                    await asyncio.sleep(0)
                    continue
                parsed = _parse_message(msg)
                if parsed is None:
                    continue
                channel, event, data, except_socket_id = parsed
                await on_message(channel, event, data, except_socket_id)

        self._tasks.append(asyncio.create_task(_pump()))


def _decode(value: object) -> str | None:
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode()
    if isinstance(value, str):
        return value
    return None


def _decode_envelope(msg: object) -> tuple[str, dict[str, object]] | None:
    """Pull (broadcast channel, JSON body) from a raw pmessage, or None on bad shape."""
    if not isinstance(msg, dict):
        return None
    msg_typed = cast("dict[Any, Any]", msg)  # type: ignore[redundant-cast]

    redis_channel = _decode(msg_typed.get("channel"))
    if redis_channel is None or not redis_channel.startswith(_CHANNEL_PREFIX):
        return None

    payload_str = _decode(msg_typed.get("data"))
    if payload_str is None:
        return None
    try:
        body_raw: object = json.loads(payload_str)
    except TypeError, ValueError:
        return None
    if not isinstance(body_raw, dict):
        return None
    body = {str(k): v for k, v in cast("dict[Any, Any]", body_raw).items()}  # type: ignore[redundant-cast]
    return redis_channel[len(_CHANNEL_PREFIX) :], body


def _parse_message(
    msg: object,
) -> tuple[str, str, dict[str, object], str | None] | None:
    """Decode a pmessage into (channel, event, data, except_socket_id), or None on bad shape."""
    envelope = _decode_envelope(msg)
    if envelope is None:
        return None
    channel, body = envelope

    event = body.get("event")
    if not isinstance(event, str):
        return None
    data_v = body.get("data", {})
    data: dict[str, object] = (
        {str(k): v for k, v in cast("dict[Any, Any]", data_v).items()}  # type: ignore[redundant-cast]
        if isinstance(data_v, dict)
        else {}
    )
    except_v = body.get("except_socket_id")
    except_socket_id = except_v if isinstance(except_v, str) else None
    return channel, event, data, except_socket_id


__all__ = ["AsyncRedis", "OnMessage", "RedisBus"]
