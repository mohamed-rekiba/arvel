"""Tests for NotificationManager."""

from __future__ import annotations

import pytest
from arvel.notifications.manager import NotificationManager

from .helpers import (
    DbOnlyNotification,
    FakeUser,
    WelcomeNotification,
)


class TestNotificationManager:
    def _make_manager(self) -> NotificationManager:
        from arvel.container import Container
        from arvel.mail.config import MailConfig
        from arvel.mail.drivers.array import ArrayMailDriver
        from arvel.mail.mailer import Mailer

        container = Container()
        mailer = Mailer(default_driver=ArrayMailDriver(), config=MailConfig(default="array"))
        container.instance(Mailer, mailer)
        return NotificationManager(container)

    @pytest.mark.asyncio
    async def test_send_dispatches_to_all_via_channels(self) -> None:
        manager = self._make_manager()
        user = FakeUser(1)
        notification = WelcomeNotification()
        # Should not raise; mail + database + log channels all fire
        await manager.send(user, notification)

    @pytest.mark.asyncio
    async def test_send_skips_mail_if_to_mail_returns_none(self) -> None:
        manager = self._make_manager()
        user = FakeUser(1)
        notification = DbOnlyNotification()
        # database-only — no mail sent, should not raise
        await manager.send(user, notification)

    @pytest.mark.asyncio
    async def test_channel_error_does_not_propagate(self) -> None:
        """Channel errors must not propagate to the caller."""
        from unittest.mock import AsyncMock, MagicMock

        from arvel.notifications.channels.mail_channel import MailChannel

        manager = self._make_manager()
        bad_channel = MagicMock(spec=MailChannel)
        bad_channel.send = AsyncMock(side_effect=RuntimeError("channel crashed"))
        manager.register_channel("mail", bad_channel)

        user = FakeUser(1)
        await manager.send(user, WelcomeNotification())  # must not raise

    @pytest.mark.asyncio
    async def test_unknown_channel_raises(self) -> None:
        from arvel.notifications.exceptions import UnknownChannelError
        from arvel.notifications.notification import Notification

        class BadVia(Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["nonexistent_channel"]

        manager = self._make_manager()
        with pytest.raises(UnknownChannelError):
            await manager.send(FakeUser(1), BadVia())

    @pytest.mark.asyncio
    async def test_queued_notification_falls_back_to_inline_when_bus_missing(self) -> None:
        from arvel.notifications.notification import Notification
        from arvel.notifications.should_queue import ShouldQueue

        class QueuedNotification(Notification, ShouldQueue):
            def via(self, notifiable: object) -> list[str]:
                return ["record"]

        class RecordingChannel:
            def __init__(self) -> None:
                self.sent = 0

            async def send(self, notifiable: object, notification: Notification) -> None:
                self.sent += 1

        manager = self._make_manager()
        channel = RecordingChannel()
        manager.register_channel("record", channel)

        await manager.send(FakeUser(1), QueuedNotification())
        await manager.send_now(FakeUser(1), QueuedNotification())

        assert channel.sent == 2
