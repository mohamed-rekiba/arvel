"""LogChannel — logs notification to structlog (FR-009-027)."""

from __future__ import annotations

from typing import Any

from arvel.logging.facade import Log
from arvel.notifications.notification import Notification

logger = Log.channel(__name__)


class LogChannel:
    """Logs notification type and notifiable identity at INFO. Never raises."""

    async def send(self, notifiable: Any, notification: Notification) -> None:
        try:
            logger.info(
                "notification_sent",
                channel="log",
                type=type(notification).__name__,
                notifiable=type(notifiable).__name__,
                notifiable_id=str(getattr(notifiable, "id", "?")),
            )
        # Log-channel failures must not break notification dispatch.
        except Exception:  # nosec B110
            pass


__all__ = ["LogChannel"]
