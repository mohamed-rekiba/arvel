"""RedisBus — cross-process fan-out for Reverb."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from arvel.broadcasting.config import ReverbConfig


class _AsyncPubSub(Protocol):
    async def subscribe(self, *channels: str) -> None: ...

    async def get_message(
        self, *, ignore_subscribe_messages: bool = True, timeout: float | None = None
    ) -> Any: ...


class _AsyncRedis(Protocol):
    def pubsub(self) -> _AsyncPubSub: ...

    async def publish(self, channel: str, message: str) -> int: ...


_PATTERN = "arvel.reverb.broadcast"


class RedisBus:
    """Pub/Sub bridge so multiple Reverb processes share the same fan-out."""

    def __init__(self, *, redis: _AsyncRedis, config: ReverbConfig) -> None:
        self._redis: _AsyncRedis = redis
        self._config: ReverbConfig = config
        self._origin: str = secrets.token_hex(8)
        self._tasks: list[asyncio.Task[None]] = []

    async def publish(
        self,
        channel: str,
        event: str,
        data: dict[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        body = json.dumps(
            {
                "origin": self._origin,
                "channel": channel,
                "event": event,
                "data": data,
                "except_socket_id": except_socket_id,
            }
        )
        await self._redis.publish(_PATTERN, body)

    async def subscribe(
        self,
        on_message: Callable[[str, str, dict[str, object]], Awaitable[None]],
    ) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_PATTERN)

        async def _pump() -> None:
            while True:
                msg: object = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if msg is None:
                    await asyncio.sleep(0)
                    continue
                envelope = _parse_envelope(msg)
                if envelope is None or envelope.get("origin") == self._origin:
                    continue
                args = _extract_callback_args(envelope)
                if args is None:
                    continue
                channel_v, event_v, payload_dict = args
                await on_message(channel_v, event_v, payload_dict)

        self._tasks.append(asyncio.create_task(_pump()))


def _parse_envelope(msg: object) -> dict[str, object] | None:
    """Decode a raw pubsub message into the envelope dict, or ``None`` on bad shape."""
    if not isinstance(msg, dict):
        return None
    msg_typed = cast("dict[Any, Any]", msg)  # type: ignore[redundant-cast]
    raw_payload: object = msg_typed.get("data")
    if isinstance(raw_payload, bytes | bytearray):
        payload_str = bytes(raw_payload).decode()
    elif isinstance(raw_payload, str):
        payload_str = raw_payload
    else:
        return None
    try:
        body_raw: object = json.loads(payload_str)
    except TypeError, ValueError:
        return None
    if not isinstance(body_raw, dict):
        return None
    body_typed = cast("dict[Any, Any]", body_raw)  # type: ignore[redundant-cast]
    return {str(k): v for k, v in body_typed.items()}


def _extract_callback_args(
    body: dict[str, object],
) -> tuple[str, str, dict[str, object]] | None:
    """Pull (channel, event, payload) from a validated envelope, or ``None``."""
    channel_v = body.get("channel")
    event_v = body.get("event")
    data_v = body.get("data", {})
    if not (isinstance(channel_v, str) and isinstance(event_v, str)):
        return None
    if isinstance(data_v, dict):
        data_typed = cast("dict[Any, Any]", data_v)  # type: ignore[redundant-cast]
        payload_dict: dict[str, object] = {str(k): v for k, v in data_typed.items()}
    else:
        payload_dict = {}
    return channel_v, event_v, payload_dict


__all__ = ["RedisBus"]
