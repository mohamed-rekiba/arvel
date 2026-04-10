"""Tests for NotificationContract and channels — Story 4.

FR-100: NotificationContract with send(notifiable, notification).
FR-101: Notification base class with via(), to_mail(), to_database(), to_slack().
FR-102: Mail channel dispatches via MailContract.
FR-103: Database channel writes to notifications table.
FR-104: Slack channel sends webhook.
FR-105: ShouldQueue dispatches through QueueContract.
FR-106: NotificationFake captures for assertion.
SEC-025: Database payloads sanitized.
"""

from __future__ import annotations

import pytest

from arvel.notifications.contracts import NotificationChannel, NotificationContract
from arvel.notifications.notification import (
    DatabasePayload,
    MailMessage,
    Notification,
    ShouldQueue,
    SlackMessage,
)


class TestNotificationContractInterface:
    """FR-100: NotificationContract ABC defines send(notifiable, notification)."""

    def test_notification_contract_is_abstract(self) -> None:
        abstract_cls: type = NotificationContract
        with pytest.raises(TypeError):
            abstract_cls()

    def test_contract_has_send_method(self) -> None:
        assert hasattr(NotificationContract, "send")

    def test_channel_contract_is_abstract(self) -> None:
        abstract_cls: type = NotificationChannel
        with pytest.raises(TypeError):
            abstract_cls()


class TestNotificationBaseClass:
    """FR-101: Notification base class with via() and to_*() methods."""

    def test_default_via_returns_mail(self) -> None:
        n = Notification()
        assert n.via() == ["mail"]

    def test_to_mail_returns_mail_message(self) -> None:
        n = Notification()
        result = n.to_mail(notifiable=None)
        assert isinstance(result, MailMessage)

    def test_to_database_returns_payload(self) -> None:
        n = Notification()
        result = n.to_database(notifiable=None)
        assert isinstance(result, DatabasePayload)

    def test_to_slack_returns_slack_message(self) -> None:
        n = Notification()
        result = n.to_slack(notifiable=None)
        assert isinstance(result, SlackMessage)

    def test_custom_notification_via(self) -> None:
        class OrderShipped(Notification):
            def via(self):
                return ["mail", "database"]

        n = OrderShipped()
        assert n.via() == ["mail", "database"]


class TestShouldQueueMixin:
    """FR-105: Notifications with ShouldQueue are dispatched via QueueContract."""

    def test_should_queue_is_mixin(self) -> None:
        class QueuedNotification(ShouldQueue, Notification):
            pass

        n = QueuedNotification()
        assert isinstance(n, ShouldQueue)
        assert isinstance(n, Notification)


class TestNotificationFake:
    """FR-106: NotificationFake captures all notifications for assertion."""

    async def test_fake_implements_contract(self) -> None:
        from arvel.notifications.fakes import NotificationFake

        fake = NotificationFake()
        assert isinstance(fake, NotificationContract)

    async def test_fake_records_sent(self) -> None:
        from arvel.notifications.fakes import NotificationFake

        fake = NotificationFake()
        n = Notification()
        await fake.send("user_1", n)
        assert fake.sent_count == 1

    async def test_fake_assert_sent_to(self) -> None:
        from arvel.notifications.fakes import NotificationFake

        fake = NotificationFake()
        await fake.send("user_1", Notification())
        fake.assert_sent_to("user_1")

    async def test_fake_assert_nothing_sent(self) -> None:
        from arvel.notifications.fakes import NotificationFake

        fake = NotificationFake()
        fake.assert_nothing_sent()

    async def test_fake_assert_sent_type(self) -> None:
        from arvel.notifications.fakes import NotificationFake

        class OrderShipped(Notification):
            pass

        fake = NotificationFake()
        await fake.send("user_1", OrderShipped())
        fake.assert_sent_type(OrderShipped)


class TestNotificationConfig:
    """NFR-038: NotificationSettings uses NOTIFICATION_ env prefix."""

    def test_defaults(self, clean_env: None) -> None:
        from arvel.notifications.config import NotificationSettings

        settings = NotificationSettings()
        assert settings.default_channels == ["mail"]
        assert settings.database_table == "notifications"

    def test_slack_webhook_is_secret(self) -> None:
        from arvel.notifications.config import NotificationSettings

        settings = NotificationSettings()
        assert hasattr(settings.slack_webhook_url, "get_secret_value")
