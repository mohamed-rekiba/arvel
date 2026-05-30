"""Tests for NotificationServiceProvider — FR-009-031."""

from __future__ import annotations

import pytest
from arvel import Application
from arvel.notifications.manager import NotificationManager
from arvel.notifications.providers.notification_service_provider import NotificationServiceProvider


class TestNotificationServiceProvider:
    def test_register_binds_manager(self) -> None:
        app = Application()
        provider = NotificationServiceProvider(app)
        provider.register()
        manager = app.container.make(NotificationManager)
        assert isinstance(manager, NotificationManager)

    @pytest.mark.asyncio
    async def test_boot_binds_notification_facade(self) -> None:
        from arvel.facades.notification import Notification as NotificationFacade

        app = Application()
        provider = NotificationServiceProvider(app)
        provider.register()
        await provider.boot()
        assert NotificationFacade.get_manager() is not None
