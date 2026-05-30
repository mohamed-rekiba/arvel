"""Tests for Notification facade — FR-009-030."""

from __future__ import annotations

import pytest

from .helpers import FakeUser, WelcomeNotification


class TestNotificationFacade:
    def teardown_method(self) -> None:
        from arvel.facades.notification import Notification as NotificationFacade

        NotificationFacade.reset()

    @pytest.mark.asyncio
    async def test_send_raises_when_not_bound(self) -> None:
        from arvel.facades.notification import Notification as NotificationFacade
        from arvel.queue.exceptions import FacadeNotBoundError

        with pytest.raises(FacadeNotBoundError):
            await NotificationFacade.send(FakeUser(1), WelcomeNotification())

    @pytest.mark.asyncio
    async def test_send_proxies_to_manager(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from arvel.facades.notification import Notification as NotificationFacade
        from arvel.notifications.manager import NotificationManager

        manager = MagicMock(spec=NotificationManager)
        manager.send = AsyncMock()
        NotificationFacade.bind(manager)

        user = FakeUser(1)
        notification = WelcomeNotification()
        await NotificationFacade.send(user, notification)
        manager.send.assert_called_once_with(user, notification)
