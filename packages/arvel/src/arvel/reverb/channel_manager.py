"""ChannelManager — in-process pub/sub for the Reverb WS server (FR-013-025, NFR-013-006)."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol

from arvel.reverb.protocol import build_event_frame

logger = logging.getLogger(__name__)


class _Sendable(Protocol):
    async def send(self, frame: str) -> None: ...


class ChannelManager:
    """Tracks `channel → set[connection]` and fans out events.

    Connection identity comes from object identity (`id(conn)`), so any object
    with an async `send(frame)` method qualifies.
    """

    def __init__(self) -> None:
        self._channels: dict[str, list[object]] = {}

    def subscribe(self, channel: str, connection: object) -> None:
        bucket = self._channels.setdefault(channel, [])
        if connection not in bucket:
            bucket.append(connection)

    def unsubscribe(self, channel: str, connection: object) -> None:
        bucket = self._channels.get(channel)
        if not bucket:
            return
        try:
            bucket.remove(connection)
        except ValueError:
            return
        if not bucket:
            # Prevent unbounded channel-name growth (MEDIUM-2, Stage 4b).
            del self._channels[channel]

    def subscribers(self, channel: str) -> list[object]:
        return list(self._channels.get(channel, []))

    async def publish(
        self,
        channel: str,
        event: str,
        data: dict[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        frame = build_event_frame(channel=channel, event=event, data=data)
        for conn in list(self._channels.get(channel, [])):
            sid = getattr(conn, "socket_id", None)
            if except_socket_id is not None and sid == except_socket_id:
                continue
            sendable = self._as_sendable(conn)
            try:
                await sendable.send(frame)
            except Exception:
                logger.warning(
                    "reverb_send_failed_unsubscribing channel=%s socket_id=%s",
                    channel,
                    sid,
                )
                self.unsubscribe(channel, conn)

    @staticmethod
    def _as_sendable(connection: object) -> _Sendable:
        # Trust the duck-type: every caller in this package implements send().
        return connection  # type: ignore[return-value]

    def channels_for(self, connection: object) -> Iterable[str]:
        return [c for c, conns in self._channels.items() if connection in conns]


__all__ = ["ChannelManager"]
