"""``make:notification`` — generate a multi-channel notification.

A Notification routes a single piece of news through one or more channels.
:meth:`via` lists the channel names; for each channel, the matching
``to_*`` method (``to_mail``, ``to_database``, ``to_broadcast``) returns
the payload for that channel.

Built-in channel names: ``"mail"``, ``"database"``, ``"broadcast"``,
``"log"``. Operators can register custom channels via
``NotificationManager.register_channel(name, channel)``.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — multi-channel notification."""

from __future__ import annotations

from typing import Any

from arvel.notifications import Notification


class {title}(Notification):
    """A notification deliverable through mail, database, and broadcast."""

    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable: Any) -> Any:
        # Return a Mailable here when ``"mail"`` is in ``via()``.
        # Example:
        #   from app.mail.welcome_mail import WelcomeMail
        #   return WelcomeMail(user=notifiable)
        return None

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return {{"type": "{title}", "notifiable_id": getattr(notifiable, "id", None)}}

    def to_broadcast(self, notifiable: Any) -> dict[str, Any]:
        return {{
            "channels": [f"private-user.{{getattr(notifiable, 'id', '')}}"],
            "data": {{"type": "{title}"}},
        }}
'''


class MakeNotificationCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:notification"
    help: ClassVar[str] = "Generate a Notification (via + to_mail/to_database/to_broadcast)"
    _target_subdir: ClassVar[str] = "app/notifications"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
