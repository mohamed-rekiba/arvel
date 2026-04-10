"""Tests for notification channel dispatchers — FR-102, FR-103, FR-104.

Tests the concrete NotificationDispatcher and individual channels.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arvel.notifications.contracts import NotificationChannel, NotificationContract
from arvel.notifications.notification import (
    DatabasePayload,
    MailMessage,
    Notification,
    SlackMessage,
)


class OrderShipped(Notification):
    """Test notification used across channel tests."""

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id

    def via(self) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable: Any) -> MailMessage:
        return MailMessage(
            subject=f"Order #{self.order_id} Shipped",
            body=f"Your order #{self.order_id} has been shipped.",
        )

    def to_database(self, notifiable: Any) -> DatabasePayload:
        return DatabasePayload(
            type="order_shipped",
            data={"order_id": self.order_id},
        )


class SlackNotification(Notification):
    """Test notification for Slack channel."""

    def via(self) -> list[str]:
        return ["slack"]

    def to_slack(self, notifiable: Any) -> SlackMessage:
        return SlackMessage(text="Deploy completed")


class TestNotificationDispatcher:
    """B4: NotificationDispatcher routes to channels via notification.via()."""

    def test_dispatcher_implements_contract(self) -> None:
        from arvel.notifications.dispatcher import NotificationDispatcher

        assert issubclass(NotificationDispatcher, NotificationContract)

    async def test_dispatches_to_mail_and_database_channels(self) -> None:
        from arvel.notifications.dispatcher import NotificationDispatcher

        mail_channel = AsyncMock(spec=NotificationChannel)
        db_channel = AsyncMock(spec=NotificationChannel)
        dispatcher = NotificationDispatcher(channels={"mail": mail_channel, "database": db_channel})
        user = {"id": 1, "email": "user@test.com"}
        notification = OrderShipped(order_id=42)

        await dispatcher.send(user, notification)

        mail_channel.deliver.assert_awaited_once_with(user, notification)
        db_channel.deliver.assert_awaited_once_with(user, notification)

    async def test_skips_unregistered_channels(self) -> None:
        from arvel.notifications.dispatcher import NotificationDispatcher

        mail_channel = AsyncMock(spec=NotificationChannel)
        dispatcher = NotificationDispatcher(channels={"mail": mail_channel})
        user = {"id": 1}
        notification = OrderShipped(order_id=42)

        await dispatcher.send(user, notification)

        mail_channel.deliver.assert_awaited_once()

    async def test_raises_on_channel_error(self) -> None:
        from arvel.notifications.dispatcher import NotificationDispatcher
        from arvel.notifications.exceptions import NotificationChannelError

        failing_channel = AsyncMock(spec=NotificationChannel)
        failing_channel.deliver.side_effect = Exception("Channel broke")
        dispatcher = NotificationDispatcher(channels={"mail": failing_channel})

        with pytest.raises(NotificationChannelError):
            await dispatcher.send({"id": 1}, OrderShipped(42))


class TestMailChannel:
    """FR-102: MailChannel creates Mailable from to_mail() and dispatches via MailContract."""

    def test_mail_channel_implements_channel_contract(self) -> None:
        from arvel.notifications.channels.mail_channel import MailChannel

        assert issubclass(MailChannel, NotificationChannel)

    async def test_delivers_via_mail_contract(self) -> None:
        from arvel.notifications.channels.mail_channel import MailChannel

        mock_mailer = AsyncMock()
        channel = MailChannel(mailer=mock_mailer)
        user = MagicMock()
        user.email = "user@test.com"
        notification = OrderShipped(order_id=42)

        await channel.deliver(user, notification)

        mock_mailer.send.assert_awaited_once()
        sent_mailable = mock_mailer.send.call_args[0][0]
        assert "user@test.com" in sent_mailable.to
        assert "Order #42 Shipped" in sent_mailable.subject

    async def test_uses_notifiable_email_attribute(self) -> None:
        from arvel.notifications.channels.mail_channel import MailChannel

        mock_mailer = AsyncMock()
        channel = MailChannel(mailer=mock_mailer)
        user = MagicMock()
        user.email = "specific@test.com"

        await channel.deliver(user, OrderShipped(1))

        sent_mailable = mock_mailer.send.call_args[0][0]
        assert "specific@test.com" in sent_mailable.to


class TestDatabaseChannel:
    """FR-103: DatabaseChannel writes record to notifications table."""

    def test_db_channel_implements_channel_contract(self) -> None:
        from arvel.notifications.channels.database_channel import DatabaseChannel

        assert issubclass(DatabaseChannel, NotificationChannel)

    async def test_writes_notification_record(self) -> None:
        from arvel.notifications.channels.database_channel import DatabaseChannel

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = AsyncMock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        channel = DatabaseChannel(session_factory=mock_session_factory)
        user = MagicMock()
        user.__class__.__name__ = "User"
        user.id = 1
        notification = OrderShipped(order_id=42)

        await channel.deliver(user, notification)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()


class TestSlackChannel:
    """FR-104: SlackChannel sends webhook message from to_slack()."""

    def test_slack_channel_implements_channel_contract(self) -> None:
        from arvel.notifications.channels.slack_channel import SlackChannel

        assert issubclass(SlackChannel, NotificationChannel)

    async def test_sends_webhook_via_httpx(self) -> None:
        from arvel.notifications.channels.slack_channel import SlackChannel

        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        with patch("arvel.notifications.channels.slack_channel.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_httpx.AsyncClient.return_value = mock_client

            await channel.deliver(MagicMock(), SlackNotification())

            mock_client.post.assert_awaited_once()
            call_kwargs = mock_client.post.call_args
            assert "hooks.slack.com" in str(call_kwargs)

    async def test_raises_on_webhook_failure(self) -> None:
        from arvel.notifications.channels.slack_channel import SlackChannel
        from arvel.notifications.exceptions import NotificationChannelError

        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        with patch("arvel.notifications.channels.slack_channel.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.side_effect = Exception("Connection failed")
            mock_httpx.AsyncClient.return_value = mock_client

            with pytest.raises(NotificationChannelError):
                await channel.deliver(MagicMock(), SlackNotification())
