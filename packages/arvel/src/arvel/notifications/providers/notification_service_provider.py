"""NotificationServiceProvider — registers NotificationManager and Notification facade."""

from __future__ import annotations

from pathlib import Path

from arvel.notifications.manager import NotificationManager
from arvel.providers.service_provider import ServiceProvider


class NotificationServiceProvider(ServiceProvider):
    """Registers NotificationManager and wires the Notification facade."""

    def register(self) -> None:
        manager = NotificationManager(container=self.container)
        self.container.instance(NotificationManager, manager)

    async def boot(self) -> None:
        from arvel.facades.notification import Notification as NotificationFacade
        from arvel.notifications import migrations as notif_migrations

        manager = self.container.make(NotificationManager)
        NotificationFacade.bind(manager)

        stub = Path(notif_migrations.__file__).parent / "create_notifications_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-notifications",
            is_migrations=True,
        )


__all__ = ["NotificationServiceProvider"]
