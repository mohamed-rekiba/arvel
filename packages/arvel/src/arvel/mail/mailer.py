"""Mailer — renders mailables and delegates to the active driver."""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from arvel.logging.facade import Log
from arvel.mail.config import MailConfig
from arvel.mail.pending_send import MailPendingSend
from arvel.mail.rendered_mail import RenderedMail

if TYPE_CHECKING:
    from arvel.mail.drivers.array import ArrayMailDriver
    from arvel.mail.drivers.log import LogMailDriver
    from arvel.mail.drivers.smtp import SmtpMailDriver
    from arvel.mail.mailable import Mailable

MailDriver = Union["ArrayMailDriver", "LogMailDriver", "SmtpMailDriver"]

logger = Log.channel(__name__)


class Mailer:
    """Renders a Mailable and sends it via the configured driver."""

    def __init__(self, default_driver: MailDriver, config: MailConfig) -> None:
        self._default_driver: MailDriver = default_driver
        self._config = config

    @property
    def current_driver(self) -> MailDriver:
        """Return the active mail driver."""
        return self._default_driver

    def swap_driver(self, driver: MailDriver) -> MailDriver:
        """Swap the active driver, returning the previous one."""
        old = self._default_driver
        self._default_driver = driver
        return old

    def to(self, address: object) -> MailPendingSend:
        """Begin a fluent send chain. ``address`` may be a string or an object with ``.email``."""
        addr = address if isinstance(address, str) else str(getattr(address, "email", str(address)))
        return MailPendingSend(self, addr)

    async def send_to(self, address: str, mailable: Mailable) -> None:
        rendered = self._render(mailable, override_to=[address])
        await self._default_driver.send(rendered)

    def _render(self, mailable: Mailable, override_to: list[str] | None = None) -> RenderedMail:
        env = mailable.envelope()
        content = mailable.content()
        attachments = mailable.attachments()

        body_html: str | None = None
        body_text: str | None = None

        # HTML body — explicit string or rendered template
        if content.html_view is not None:
            from arvel.support.view import render_template

            body_html = render_template(content.html_view, content.data)
        elif content.html is not None:
            body_html = content.html

        # Plain-text body — explicit string or rendered template
        if content.text_view is not None:
            from arvel.support.view import render_template

            body_text = render_template(content.text_view, content.data)
        elif content.text is not None:
            body_text = content.text

        # Auto-derive a plain-text alternative when only HTML was supplied.
        # Real mailers should provide both bodies explicitly, but auto-derive
        # protects accessibility and spam scoring when they don't.
        if body_html is not None and body_text is None:
            from arvel.support.html_to_text import html_to_text

            body_text = html_to_text(body_html)

        # Defensive default — Content validation prevents reaching here with
        # neither body set, but the RenderedMail contract requires str.
        if body_text is None:
            body_text = ""

        if override_to:
            from dataclasses import replace

            env = replace(env, to=override_to)

        return RenderedMail(
            envelope=env,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
        )


__all__ = ["MailDriver", "Mailer"]
