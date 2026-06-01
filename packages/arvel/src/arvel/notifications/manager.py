"""NotificationManager — channel dispatch orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from arvel.logging.facade import Log
from arvel.notifications.exceptions import UnknownChannelError
from arvel.notifications.notification import Notification

if TYPE_CHECKING:
    from arvel.container import Container

logger = Log.channel(__name__)


class NotificationManager:
    """Resolves channel objects and dispatches notifications through them.

    Raises UnknownChannelError for unregistered channel names.
    Per-channel errors are caught and logged; remaining channels still run.
    """

    def __init__(self, container: Container) -> None:
        self._container = container
        self._channels: dict[str, Any] = {}
        self._bootstrap_channels()

    def _bootstrap_channels(self) -> None:
        from arvel.notifications.channels.broadcast_channel import BroadcastChannel
        from arvel.notifications.channels.log_channel import LogChannel

        self._channels["log"] = LogChannel()
        self._channels["broadcast"] = BroadcastChannel()

        # mail channel — uses Mailer if bound
        try:
            from arvel.mail.mailer import Mailer
            from arvel.notifications.channels.mail_channel import MailChannel

            mailer = self._container.make(Mailer)
            self._channels["mail"] = MailChannel(mailer)
        # Mail channel is optional; skip silently if Mailer isn't bound.
        except Exception:  # nosec B110
            pass

        # database channel — uses session factory if available
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            from arvel.notifications.channels.database_channel import (
                DatabaseChannel,
            )

            factory = self._container.make(async_sessionmaker[AsyncSession])
            self._channels["database"] = DatabaseChannel(session_factory=factory)
        # Database channel is optional; skip if SQLAlchemy session factory isn't bound.
        except Exception:  # nosec B110
            pass

    async def send(self, notifiable: Any, notification: Notification) -> None:
        """Send notification. If notification implements ShouldQueue, dispatches via queue."""
        from arvel.notifications.should_queue import ShouldQueue

        if isinstance(notification, ShouldQueue):
            await self.send_via_queue(notifiable, notification)
            return
        await self._send_inline(notifiable, notification)

    async def send_via_queue(self, notifiable: Any, notification: Notification) -> None:
        """Enqueue a ShouldQueue notification for background processing."""
        try:
            from arvel.queue.bus import Bus

            bus = self._container.make(Bus)
            from arvel.notifications.notification_job import NotificationJob

            notifiable_cls = cast("type[object]", type(notifiable))
            job = NotificationJob(
                notifiable_id=str(getattr(notifiable, "id", "")),
                notifiable_class=f"{notifiable_cls.__module__}.{notifiable_cls.__qualname__}",
                notification_class=(
                    f"{type(notification).__module__}.{type(notification).__qualname__}"
                ),
            )
            await bus.dispatch(job)
        except Exception:
            # Queue not configured — fall back to inline send so the app doesn't break.
            logger.warning(
                "notification_queue_fallback",
                notification=type(notification).__name__,
            )
            await self._send_inline(notifiable, notification)

    async def _send_inline(self, notifiable: Any, notification: Notification) -> None:
        channels = notification.via(notifiable)
        for channel_name in channels:
            if channel_name not in self._channels:
                raise UnknownChannelError(channel_name)
            channel = self._channels[channel_name]
            try:
                await channel.send(notifiable, notification)
            except Exception:
                logger.exception(
                    "notification_channel_error",
                    channel=channel_name,
                    notification=type(notification).__name__,
                )

    def register_channel(self, name: str, channel: Any) -> None:
        """Register a named channel, replacing any existing one with the same name."""
        self._channels[name] = channel

    async def send_now(self, notifiable: Any, notification: Notification) -> None:
        """Send inline, bypassing the queue even for ShouldQueue notifications."""
        await self._send_inline(notifiable, notification)


__all__ = ["NotificationManager"]
