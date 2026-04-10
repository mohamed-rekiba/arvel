"""Mail notification channel — builds a Mailable and sends via MailContract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.mail.mailable import Mailable
from arvel.notifications.contracts import NotificationChannel

if TYPE_CHECKING:
    from typing import Any

    from arvel.mail.contracts import MailContract
    from arvel.notifications.notification import Notification


class MailChannel(NotificationChannel):
    """Delivers notifications through the configured mail backend."""

    def __init__(self, mailer: MailContract) -> None:
        self._mailer = mailer

    async def deliver(self, notifiable: Any, notification: Notification) -> None:
        mail_message = notification.to_mail(notifiable)
        mailable = Mailable(
            to=[notifiable.email],
            subject=mail_message.subject,
            body=mail_message.body,
            template=mail_message.template,
            context=mail_message.context,
        )
        await self._mailer.send(mailable)
