"""NotificationServiceProvider — binds the Notification manager (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.notifications import NotificationManager

if TYPE_CHECKING:
    from arvel.contracts import Container


class NotificationServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_notifications(app: Container) -> NotificationManager:
            return NotificationManager(app)

        self.app.singleton("notifications", make_notifications)

    def boot(self) -> None:
        """No-op."""
