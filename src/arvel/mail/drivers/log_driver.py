"""LogMailer — logs email content for development."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.logging import Log
from arvel.mail.contracts import MailContract

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable

logger = Log.named("arvel.mail.drivers.log_driver")


class LogMailer(MailContract):
    """Logs the full email to the logger instead of sending."""

    async def send(self, mailable: Mailable) -> None:
        logger.info(
            "Mail sent (log driver)",
            extra={
                "to": mailable.to,
                "subject": mailable.subject,
                "template": mailable.template,
                "has_body": bool(mailable.body or mailable.html_body),
                "attachments": len(mailable.attachments),
            },
        )
