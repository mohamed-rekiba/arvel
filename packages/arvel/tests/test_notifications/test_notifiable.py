"""Tests for Notifiable mixin."""

from __future__ import annotations

import pytest
from arvel.notifications.notifiable import Notifiable

from .helpers import WelcomeNotification


class NotifiableUser(Notifiable):
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.email = "user@example.com"


class TestNotifiable:
    def test_notifiable_adds_notify_method(self) -> None:
        user = NotifiableUser(1)
        assert hasattr(user, "notify")

    def test_notifiable_adds_notify_now_method(self) -> None:
        user = NotifiableUser(1)
        assert hasattr(user, "notify_now")

    @pytest.mark.asyncio
    async def test_notify_dispatches_notification(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from arvel.notifications.manager import NotificationManager

        manager = MagicMock(spec=NotificationManager)
        manager.send = AsyncMock()

        user = NotifiableUser(1)
        user.notification_manager = manager
        notification = WelcomeNotification()
        await user.notify(notification)
        manager.send.assert_called_once_with(user, notification)

    @pytest.mark.asyncio
    async def test_notify_now_calls_send_now(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from arvel.notifications.manager import NotificationManager

        manager = MagicMock(spec=NotificationManager)
        manager.send_now = AsyncMock()

        user = NotifiableUser(1)
        user.notification_manager = manager
        await user.notify_now(WelcomeNotification())
        manager.send_now.assert_called_once()
