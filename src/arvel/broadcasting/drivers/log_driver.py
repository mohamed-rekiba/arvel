"""LogBroadcaster — logs broadcasts via structlog for debugging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.broadcasting.contracts import BroadcastContract
from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel

logger = Log.named("arvel.broadcasting.log_driver")


class LogBroadcaster(BroadcastContract):
    """Logs every broadcast via structlog. Useful for debugging in development."""

    async def broadcast(
        self,
        channels: list[Channel],
        event: str,
        data: dict[str, Any],
    ) -> None:
        channel_names = [ch.name for ch in channels]
        logger.info(
            "broadcast",
            event_name=event,
            channels=channel_names,
            data_keys=list(data.keys()),
        )
