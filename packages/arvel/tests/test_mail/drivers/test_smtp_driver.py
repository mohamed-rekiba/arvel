"""Tests for SmtpMailDriver — ."""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart

import pytest
from arvel.mail.config import MailEncryption, SmtpConfig
from pydantic import SecretStr


async def _capture_sent_message(*, from_name: str | None) -> MIMEMultipart:
    """Send through the public ``send()`` path and return the built MIME message.

    ``_send_raw`` is patched (string-based) to intercept the message instead of
    talking to a real SMTP server — the same pattern the failure test uses.
    """
    from arvel.mail.drivers.smtp import SmtpMailDriver
    from arvel.mail.envelope import Envelope
    from arvel.mail.rendered_mail import RenderedMail

    driver = SmtpMailDriver(SmtpConfig(host="localhost", port=1025, encryption=None))
    rendered = RenderedMail(
        envelope=Envelope(
            from_address="bot@x.com",
            from_name=from_name,
            to=["c@d.com"],
            subject="Hi",
        ),
        body_text="x",
        body_html=None,
        attachments=[],
    )
    captured: dict[str, MIMEMultipart] = {}

    async def _fake_send_raw(msg: MIMEMultipart, recipients: list[str]) -> None:
        captured["msg"] = msg

    from unittest.mock import patch

    with patch.object(driver, "_send_raw", _fake_send_raw):
        await driver.send(rendered)
    return captured["msg"]


class TestSmtpDriver:
    def test_smtp_driver_import_is_available(self) -> None:
        from arvel.mail.drivers.smtp import SmtpMailDriver

        assert SmtpMailDriver is not None

    def test_smtp_config_has_required_fields(self) -> None:
        cfg = SmtpConfig(host="smtp.example.com", port=587)
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 587

    def test_smtp_password_not_in_repr(self) -> None:
        """: SMTP password must never appear in logs/repr."""
        cfg = SmtpConfig(
            host="smtp.example.com",
            port=587,
            username="user",
            password=SecretStr("secret123"),
        )
        assert "secret123" not in repr(cfg)
        assert "secret123" not in str(cfg)

    def test_smtp_driver_warns_when_tls_disabled(self) -> None:
        """: emit UserWarning when encryption=None outside test."""
        from types import SimpleNamespace

        from arvel.config._lookup_registry import register
        from arvel.mail.drivers.smtp import SmtpMailDriver

        register("app", SimpleNamespace(env="production", is_production=True))
        cfg = SmtpConfig(host="smtp.example.com", port=25, encryption=None)
        with pytest.warns(UserWarning, match="TLS"):
            SmtpMailDriver(cfg)

    @pytest.mark.asyncio
    async def test_from_header_includes_display_name(self) -> None:
        """A from_name renders as ``"Name" <addr>`` per RFC 5322."""
        msg = await _capture_sent_message(from_name="Arvel Store")
        assert msg["From"] == "Arvel Store <bot@x.com>"

    @pytest.mark.asyncio
    async def test_from_header_bare_address_when_no_name(self) -> None:
        msg = await _capture_sent_message(from_name=None)
        assert msg["From"] == "bot@x.com"

    @pytest.mark.asyncio
    async def test_smtp_driver_raises_mail_exception_on_failure(self) -> None:
        """raises MailException wrapping aiosmtplib error."""
        from unittest.mock import AsyncMock, patch

        from arvel.mail.content import Content
        from arvel.mail.drivers.smtp import SmtpMailDriver
        from arvel.mail.envelope import Envelope
        from arvel.mail.exceptions import MailException
        from arvel.mail.mailable import Mailable
        from arvel.mail.rendered_mail import RenderedMail

        class _TestMail(Mailable):
            def envelope(self) -> Envelope:
                return Envelope(from_address="a@b.com", to=["c@d.com"], subject="Test")

            def content(self) -> Content:
                return Content(text="test")

        cfg = SmtpConfig(host="localhost", port=9999, encryption=MailEncryption.TLS)
        driver = SmtpMailDriver(cfg)
        rendered = RenderedMail(
            envelope=_TestMail().envelope(),
            body_text="test",
            body_html=None,
            attachments=[],
        )
        with patch.object(  # noqa: SIM117
            driver, "_send_raw", AsyncMock(side_effect=OSError("refused"))
        ):
            with pytest.raises(MailException):
                await driver.send(rendered)
