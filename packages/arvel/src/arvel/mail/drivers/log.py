"""LogMailDriver — writes sent mail to the structured log."""

from __future__ import annotations

from arvel.logging.facade import Log
from arvel.mail.rendered_mail import RenderedMail

logger = Log.channel(__name__)


class LogMailDriver:
    """Driver that logs envelope fields at INFO level. Never raises."""

    async def send(self, mail: RenderedMail) -> None:
        try:
            logger.info(
                "mail_sent",
                driver="log",
                from_address=mail.envelope.from_address,
                to=mail.envelope.to,
                subject=mail.envelope.subject,
                attachments=len(mail.attachments),
            )
        except Exception:  # noqa: BLE001
            logger.warning("log_driver_error", exc_info=True)


__all__ = ["LogMailDriver"]
