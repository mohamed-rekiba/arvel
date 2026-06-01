"""RedisBroadcaster — fan-out via Redis Pub/Sub."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from arvel.broadcasting.exceptions import BroadcastDriverError


class AsyncRedis(Protocol):
    """Subset of redis.asyncio.Redis we depend on."""

    async def publish(self, channel: str, message: str) -> int: ...


_CHANNEL_PREFIX = "arvel.broadcasting."


class RedisBroadcaster:
    """Publishes one Redis ``PUBLISH`` per channel under ``arvel.broadcasting.<channel>``.

    Payload encoding: ``{"event": str, "data": <payload>, "except_socket_id": str|None}``.
    """

    def __init__(self, redis: AsyncRedis) -> None:
        self._redis: AsyncRedis = redis

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        try:
            body = json.dumps(
                {
                    "event": event,
                    "data": dict(payload),
                    "except_socket_id": except_socket_id,
                }
            )
        except (TypeError, ValueError) as exc:
            raise BroadcastDriverError(
                f"RedisBroadcaster cannot serialize payload for event {event!r}: {exc}",
            ) from exc

        for channel in channels:
            await self._redis.publish(f"{_CHANNEL_PREFIX}{channel}", body)


__all__ = ["AsyncRedis", "RedisBroadcaster"]
