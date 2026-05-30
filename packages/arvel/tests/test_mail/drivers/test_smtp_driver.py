"""Tests for SmtpMailDriver — FR-009-019, NFR-009-005, NFR-009-006."""

from __future__ import annotations

import pytest
from arvel.mail.config import MailEncryption, SmtpConfig
from pydantic import SecretStr


class TestSmtpDriver:
    def test_smtp_driver_import_is_available(self) -> None:
        from arvel.mail.drivers.smtp import SmtpMailDriver

        assert SmtpMailDriver is not None

    def test_smtp_config_has_required_fields(self) -> None:
        cfg = SmtpConfig(host="smtp.example.com", port=587)
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 587

    def test_smtp_password_not_in_repr(self) -> None:
        """NFR-009-005: SMTP password must never appear in logs/repr."""
        cfg = SmtpConfig(
            host="smtp.example.com",
            port=587,
            username="user",
            password=SecretStr("secret123"),
        )
        assert "secret123" not in repr(cfg)
        assert "secret123" not in str(cfg)

    def test_smtp_driver_warns_when_tls_disabled(self) -> None:
        """NFR-009-006: emit UserWarning when encryption=None outside test."""
        from types import SimpleNamespace

        from arvel.config._lookup_registry import register
        from arvel.mail.drivers.smtp import SmtpMailDriver

        register("app", SimpleNamespace(env="production", is_production=True))
        cfg = SmtpConfig(host="smtp.example.com", port=25, encryption=None)
        with pytest.warns(UserWarning, match="TLS"):
            SmtpMailDriver(cfg)

    @pytest.mark.asyncio
    async def test_smtp_driver_raises_mail_exception_on_failure(self) -> None:
        """FR-009-019: raises MailException wrapping aiosmtplib error."""
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
