"""BroadcastChannel — real implementation (FR-013-027, ADR-039)."""

from __future__ import annotations

from typing import Any, cast

from arvel.logging.facade import Log
from arvel.notifications.notification import Notification

logger = Log.channel(__name__)


class BroadcastChannel:
    """Notification channel that routes through the Broadcast facade.

    A notification opts in by listing ``"broadcast"`` in ``via()`` and
    implementing ``to_broadcast(notifiable) -> {"channels": [...], "data": {...}}``.
    """

    async def send(self, notifiable: Any, notification: Notification) -> None:
        spec = notification.to_broadcast(notifiable)
        if "channels" not in spec:
            logger.warning(
                "broadcast_channel_skip",
                notification=type(notification).__name__,
                reason="to_broadcast_missing_channels",
            )
            return

        channels_raw: object = spec.get("channels", [])
        data_raw: object = spec.get("data", {})
        if not isinstance(channels_raw, list) or not isinstance(data_raw, dict):
            logger.warning(
                "broadcast_channel_skip",
                notification=type(notification).__name__,
                reason="bad_spec_shape",
            )
            return
        channels = cast("list[str]", channels_raw)
        data = cast("dict[str, object]", data_raw)

        from arvel.facades.broadcast import Broadcast

        if Broadcast.manager is None:
            logger.warning(
                "broadcast_channel_skip",
                notification=type(notification).__name__,
                reason="facade_not_bound",
            )
            return

        await Broadcast.send(
            channels=channels,
            event=type(notification).__name__,
            payload=data,
        )


__all__ = ["BroadcastChannel"]
