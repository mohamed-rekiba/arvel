"""SmtpMailer — sends email via aiosmtplib."""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr
from typing import TYPE_CHECKING

import aiosmtplib

from arvel.mail.contracts import MailContract
from arvel.mail.exceptions import MailSendError

if TYPE_CHECKING:
    from arvel.mail.mailable import Attachment, Mailable


class SmtpMailer(MailContract):
    """SMTP backend using aiosmtplib."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_address: str,
        from_name: str,
        template_dir: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address
        self._from_name = from_name
        self._template_dir = template_dir

    def _apply_headers(self, msg: EmailMessage, mailable: Mailable) -> None:
        msg["Subject"] = mailable.subject
        msg["From"] = formataddr((self._from_name, self._from_address))
        if mailable.to:
            msg["To"] = ", ".join(mailable.to)
        if mailable.cc:
            msg["Cc"] = ", ".join(mailable.cc)

    def _html_from_template_or_mailable(self, mailable: Mailable) -> str | None:
        if mailable.template and self._template_dir is not None:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            env = Environment(
                loader=FileSystemLoader(self._template_dir),
                autoescape=select_autoescape(("html", "htm", "xml")),
            )
            return env.get_template(mailable.template).render(**mailable.context)
        if mailable.html_body:
            return mailable.html_body
        return None

    def _set_body(self, msg: EmailMessage, mailable: Mailable, html_content: str | None) -> None:
        if html_content is not None and mailable.body:
            msg.set_content(mailable.body, charset="utf-8")
            msg.add_alternative(html_content, subtype="html", charset="utf-8")
        elif html_content is not None:
            msg.set_content(html_content, subtype="html", charset="utf-8")
        elif mailable.body:
            msg.set_content(mailable.body, charset="utf-8")
        else:
            msg.set_content("", charset="utf-8")

    def _add_attachments(self, msg: EmailMessage, attachments: list[Attachment]) -> None:
        for attachment in attachments:
            maintype, _, subtype = attachment.content_type.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(
                attachment.content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )

    async def send(self, mailable: Mailable) -> None:
        msg = EmailMessage()
        self._apply_headers(msg, mailable)

        html_content = self._html_from_template_or_mailable(mailable)
        self._set_body(msg, mailable, html_content)
        self._add_attachments(msg, mailable.attachments)

        recipients = [
            *mailable.to,
            *mailable.cc,
            *mailable.bcc,
        ]

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._host,
                port=self._port,
                username=self._username or None,
                password=self._password or None,
                use_tls=self._use_tls,
                start_tls=not self._use_tls,
                recipients=recipients,
            )
        except Exception as exc:
            raise MailSendError(
                recipient=mailable.to[0],
                driver="smtp",
                detail=str(exc),
            ) from exc
