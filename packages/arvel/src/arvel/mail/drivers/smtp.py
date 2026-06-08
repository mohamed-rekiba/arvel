"""SmtpMailDriver — sends via aiosmtplib."""

from __future__ import annotations

import importlib
import warnings
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Protocol, cast

from arvel.mail.attachment import Attachment
from arvel.mail.config import MailEncryption, SmtpConfig
from arvel.mail.exceptions import MailException
from arvel.mail.rendered_mail import RenderedMail


class _SmtpSend(Protocol):
    """Minimal interface for aiosmtplib.send used by SmtpMailDriver."""

    async def __call__(  # noqa: PLR0913
        self,
        message: MIMEMultipart,
        *,
        recipients: list[str],
        hostname: str,
        port: int,
        username: str | None = ...,
        password: str | None = ...,
        use_tls: bool = ...,
        start_tls: bool = ...,
    ) -> None: ...


class SmtpMailDriver:
    """Driver that sends real email via aiosmtplib.

    Raises MailException on delivery failure.
    Warns when TLS is not configured outside test environments.
    """

    def __init__(self, smtp_config: SmtpConfig) -> None:
        self._config = smtp_config
        from arvel.config import config

        if smtp_config.encryption is None and config("app.is_production", default=False):
            warnings.warn(
                "SmtpMailDriver: TLS is not enabled. Set MAIL_SMTP_ENCRYPTION=tls "
                "to prevent credential exposure.",
                UserWarning,
                stacklevel=2,
            )

    def _build_message(self, mail: RenderedMail) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        from_name = mail.envelope.from_name
        msg["From"] = (
            formataddr((from_name, mail.envelope.from_address))
            if from_name
            else mail.envelope.from_address
        )
        msg["To"] = ", ".join(mail.envelope.to)
        msg["Subject"] = mail.envelope.subject
        if mail.envelope.cc:
            msg["Cc"] = ", ".join(mail.envelope.cc)
        if mail.envelope.reply_to:
            msg["Reply-To"] = mail.envelope.reply_to

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(mail.body_text, "plain", "utf-8"))
        if mail.body_html:
            alt.attach(MIMEText(mail.body_html, "html", "utf-8"))
        msg.attach(alt)

        for att in mail.attachments:
            msg.attach(self._build_attachment(att))

        return msg

    @staticmethod
    def _build_attachment(att: Attachment) -> MIMEBase:
        payload = att.data
        if payload is None and att.path is not None:
            payload = Path(att.path).read_bytes()
        if payload is None:
            raise MailException(f"Attachment {att.name!r} has neither path nor data.")

        maintype, _, subtype = att.mime.partition("/")
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(payload)
        encoders.encode_base64(part)
        # add_header encodes the filename per RFC 2231 — handles quotes/non-ASCII safely.
        part.add_header("Content-Disposition", "attachment", filename=att.name)
        return part

    async def _send_raw(self, msg: MIMEMultipart, recipients: list[str]) -> None:
        """Send via aiosmtplib. Raises on failure."""
        try:
            _aiosmtplib = importlib.import_module("aiosmtplib")
        except ImportError as exc:
            raise MailException(
                "aiosmtplib is not installed. Run: pip install arvel[mail]"
            ) from exc

        _send: _SmtpSend = cast("_SmtpSend", _aiosmtplib.send)
        use_tls = self._config.encryption == MailEncryption.SSL
        start_tls = self._config.encryption == MailEncryption.TLS
        password = self._config.password.get_secret_value() if self._config.password else None

        try:
            await _send(
                msg,
                recipients=recipients,
                hostname=self._config.host,
                port=self._config.port,
                username=self._config.username or None,
                password=password,
                use_tls=use_tls,
                start_tls=start_tls,
            )
        except Exception as exc:
            raise MailException(f"SMTP send failed: {exc}") from exc

    async def send(self, mail: RenderedMail) -> None:
        msg = self._build_message(mail)
        recipients = mail.envelope.to + mail.envelope.cc + mail.envelope.bcc
        try:
            await self._send_raw(msg, recipients)
        except MailException:
            raise
        except Exception as exc:
            raise MailException(f"SMTP send failed: {exc}") from exc


__all__ = ["SmtpMailDriver"]
