"""Tests for SmtpMailer driver — FR-082.

Mocks aiosmtplib so tests run without a real SMTP server.
"""

from __future__ import annotations

from importlib import util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arvel.mail.contracts import MailContract
from arvel.mail.mailable import Attachment, Mailable

_has_aiosmtplib = util.find_spec("aiosmtplib") is not None
_requires_smtp = pytest.mark.skipif(not _has_aiosmtplib, reason="aiosmtplib not installed")


@_requires_smtp
class TestSmtpMailerDriver:
    """FR-082: SmtpMailer sends emails via aiosmtplib."""

    def test_smtp_implements_contract(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        assert issubclass(SmtpMailer, MailContract)

    async def test_send_plain_text_email(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            use_tls=True,
            from_address="noreply@test.com",
            from_name="Test",
        )
        mailable = Mailable(
            to=["user@example.com"],
            subject="Hello",
            body="Plain text body",
        )
        with patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp:
            mock_smtp.send = AsyncMock()
            await mailer.send(mailable)
            mock_smtp.send.assert_awaited_once()

    async def test_send_html_email(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="",
            password="",
            use_tls=False,
            from_address="noreply@test.com",
            from_name="Test",
        )
        mailable = Mailable(
            to=["user@example.com"],
            subject="HTML Test",
            html_body="<h1>Hello</h1>",
        )
        with patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp:
            mock_smtp.send = AsyncMock()
            await mailer.send(mailable)
            mock_smtp.send.assert_awaited_once()
            msg = mock_smtp.send.call_args[0][0]
            assert "text/html" in str(msg)

    async def test_send_with_attachments(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="",
            password="",
            use_tls=False,
            from_address="noreply@test.com",
            from_name="Test",
        )
        mailable = Mailable(
            to=["user@example.com"],
            subject="With File",
            body="See attached",
            attachments=[Attachment(filename="doc.txt", content=b"hello")],
        )
        with patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp:
            mock_smtp.send = AsyncMock()
            await mailer.send(mailable)
            mock_smtp.send.assert_awaited_once()

    async def test_send_with_cc_and_bcc(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="",
            password="",
            use_tls=False,
            from_address="noreply@test.com",
            from_name="Test",
        )
        mailable = Mailable(
            to=["to@test.com"],
            cc=["cc@test.com"],
            bcc=["bcc@test.com"],
            subject="CC/BCC Test",
            body="Body",
        )
        with patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp:
            mock_smtp.send = AsyncMock()
            await mailer.send(mailable)
            mock_smtp.send.assert_awaited_once()
            call_kwargs = mock_smtp.send.call_args
            recipients = call_kwargs[1].get("recipients", [])
            assert "bcc@test.com" in recipients

    async def test_send_raises_mail_send_error_on_failure(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer
        from arvel.mail.exceptions import MailSendError

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="",
            password="",
            use_tls=False,
            from_address="noreply@test.com",
            from_name="Test",
        )
        mailable = Mailable(to=["user@example.com"], subject="Fail", body="x")
        with patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp:
            mock_smtp.send = AsyncMock(side_effect=Exception("Connection refused"))
            with pytest.raises(MailSendError) as exc_info:
                await mailer.send(mailable)
            assert "user@example.com" in str(exc_info.value)
            assert "smtp" in exc_info.value.driver


@_requires_smtp
class TestMailTemplateRendering:
    """FR-086: Template rendering with Jinja2."""

    async def test_template_rendered_when_set(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="",
            password="",
            use_tls=False,
            from_address="noreply@test.com",
            from_name="Test",
            template_dir="/templates",
        )
        mailable = Mailable(
            to=["user@example.com"],
            subject="Welcome",
            template="welcome.html",
            context={"name": "Mo"},
        )
        with (
            patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp,
            patch("jinja2.Environment") as mock_env_cls,
        ):
            mock_env = MagicMock()
            mock_env_cls.return_value = mock_env
            mock_template = MagicMock()
            mock_template.render.return_value = "<h1>Hello Mo</h1>"
            mock_env.get_template.return_value = mock_template
            mock_smtp.send = AsyncMock()

            await mailer.send(mailable)

            mock_env.get_template.assert_called_once_with("welcome.html")
            mock_template.render.assert_called_once_with(name="Mo")

    async def test_plain_body_used_when_no_template(self) -> None:
        from arvel.mail.drivers.smtp_driver import SmtpMailer

        mailer = SmtpMailer(
            host="smtp.test.com",
            port=587,
            username="",
            password="",
            use_tls=False,
            from_address="noreply@test.com",
            from_name="Test",
        )
        mailable = Mailable(
            to=["user@example.com"],
            subject="Plain",
            body="Just text",
        )
        with patch("arvel.mail.drivers.smtp_driver.aiosmtplib") as mock_smtp:
            mock_smtp.send = AsyncMock()
            await mailer.send(mailable)
            msg = mock_smtp.send.call_args[0][0]
            assert "Just text" in str(msg)
