"""RedisBroadcaster — async Redis pub/sub broadcast driver."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson

from arvel.broadcasting.contracts import BroadcastContract
from arvel.broadcasting.exceptions import BroadcastError
from arvel.logging import Log

if TYPE_CHECKING:
    from typing import Protocol

    class _AsyncRedisClient(Protocol):
        """Minimal async Redis surface used by RedisBroadcaster."""

        async def publish(self, channel: str, message: bytes | str) -> int: ...

        async def aclose(self) -> None: ...


logger = Log.named("arvel.broadcasting.redis_driver")


class RedisBroadcaster(BroadcastContract):
    """Publishes broadcast events to Redis channels via PUBLISH.

    Each channel in the ``channels`` list receives a JSON message with the
    event name and data payload.  Subscribers (WebSocket gateway, another
    service, etc.) listen on those Redis channels with SUBSCRIBE.
    """

    def __init__(self, client: _AsyncRedisClient, prefix: str = "") -> None:
        self._client = client
        self._prefix = prefix

    async def broadcast(
        self,
        channels: list[Any],
        event: str,
        data: dict[str, Any],
    ) -> None:
        payload = self._serialize(event, data)
        for channel in channels:
            redis_channel = f"{self._prefix}{channel.name}"
            try:
                await self._client.publish(redis_channel, payload)
            except Exception as exc:
                logger.error(
                    "redis_publish_failed",
                    channel=redis_channel,
                    event_name=event,
                    error=str(exc),
                )
                raise BroadcastError(
                    f"Failed to publish '{event}' to '{redis_channel}': {exc}"
                ) from exc

        logger.debug(
            "broadcast_published",
            event_name=event,
            channels=[ch.name for ch in channels],
        )

    def _serialize(self, event: str, data: dict[str, Any]) -> bytes:
        return orjson.dumps({"event": event, "data": data})

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if callable(close):
            await close()
