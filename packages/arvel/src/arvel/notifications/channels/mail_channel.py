"""MailChannel — sends notification via Mailer (FR-009-025)."""

from __future__ import annotations

from typing import Any

from arvel.logging.facade import Log
from arvel.mail.mailer import Mailer
from arvel.notifications.notification import Notification

logger = Log.channel(__name__)


class MailChannel:
    """Delivers notification via the mail subsystem.

    Silently skips if ``notification.to_mail(notifiable)`` returns ``None``.
    """

    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def send(self, notifiable: Any, notification: Notification) -> None:
        mailable = notification.to_mail(notifiable)
        if mailable is None:
            return
        recipient = getattr(notifiable, "email", None)
        if recipient:
            await self._mailer.to(str(recipient)).send(mailable)
        else:
            env = mailable.envelope()
            if env.to:
                await self._mailer.send_to(env.to[0], mailable)


__all__ = ["MailChannel"]
