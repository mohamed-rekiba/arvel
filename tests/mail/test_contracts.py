"""Tests for MailContract and drivers — Story 2.

FR-080: MailContract ABC with send(mailable).
FR-081: Mailable base class fields.
FR-082: SmtpMailer (production) — tested in integration, not here.
FR-083: LogMailer writes to structlog.
FR-084: NullMailer discards silently.
FR-085: MailFake captures sent mailables.
FR-086: Template rendering with Jinja2.
SEC-021: SMTP creds from config, never hardcoded.
SEC-022: Email bodies must not include raw passwords/tokens.
"""

from __future__ import annotations

import pytest

from arvel.mail.contracts import MailContract
from arvel.mail.mailable import Attachment, Mailable


class TestMailContractInterface:
    """FR-080: MailContract ABC defines send(mailable)."""

    def test_mail_contract_is_abstract(self) -> None:
        abstract_cls: type = MailContract
        with pytest.raises(TypeError):
            abstract_cls()

    def test_contract_has_send_method(self) -> None:
        assert hasattr(MailContract, "send")


class TestMailable:
    """FR-081: Mailable base class with required fields."""

    def test_mailable_defaults(self) -> None:
        m = Mailable()
        assert m.to == []
        assert m.cc == []
        assert m.bcc == []
        assert m.subject == ""
        assert m.body == ""
        assert m.html_body == ""
        assert m.template == ""
        assert m.context == {}
        assert m.attachments == []

    def test_mailable_with_fields(self) -> None:
        m = Mailable(
            to=["user@example.com"],
            subject="Welcome",
            template="welcome.html",
            context={"name": "Mo"},
        )
        assert m.to == ["user@example.com"]
        assert m.subject == "Welcome"
        assert m.template == "welcome.html"
        assert m.context == {"name": "Mo"}

    def test_mailable_with_attachments(self) -> None:
        att = Attachment(filename="doc.pdf", content=b"bytes", content_type="application/pdf")
        m = Mailable(attachments=[att])
        assert len(m.attachments) == 1
        assert m.attachments[0].filename == "doc.pdf"


class TestNullMailer:
    """FR-084: NullMailer discards all emails silently."""

    async def test_null_implements_contract(self) -> None:
        from arvel.mail.drivers.null_driver import NullMailer

        mailer = NullMailer()
        assert isinstance(mailer, MailContract)

    async def test_null_send_does_nothing(self) -> None:
        from arvel.mail.drivers.null_driver import NullMailer

        mailer = NullMailer()
        m = Mailable(to=["user@example.com"], subject="Test")
        await mailer.send(m)  # no error, no side effects


class TestLogMailer:
    """FR-083: LogMailer writes email content to structlog."""

    async def test_log_implements_contract(self) -> None:
        from arvel.mail.drivers.log_driver import LogMailer

        mailer = LogMailer()
        assert isinstance(mailer, MailContract)

    async def test_log_send_writes_to_logger(self) -> None:
        from arvel.mail.drivers.log_driver import LogMailer

        mailer = LogMailer()
        m = Mailable(to=["dev@example.com"], subject="Test Email", body="Hello world")
        await mailer.send(m)  # should log, not raise


class TestMailFake:
    """FR-085: MailFake captures sent mailables for assertion."""

    async def test_fake_implements_contract(self) -> None:
        from arvel.mail.fakes import MailFake

        fake = MailFake()
        assert isinstance(fake, MailContract)

    async def test_fake_records_sent(self) -> None:
        from arvel.mail.fakes import MailFake

        fake = MailFake()
        m = Mailable(to=["user@example.com"], subject="Welcome")
        await fake.send(m)

        assert fake.sent_count == 1

    async def test_fake_assert_sent(self) -> None:
        from arvel.mail.fakes import MailFake

        fake = MailFake()
        await fake.send(Mailable(to=["a@b.com"], subject="Hello"))
        fake.assert_sent(subject="Hello")

    async def test_fake_assert_nothing_sent(self) -> None:
        from arvel.mail.fakes import MailFake

        fake = MailFake()
        fake.assert_nothing_sent()

    async def test_fake_assert_sent_to(self) -> None:
        from arvel.mail.fakes import MailFake

        fake = MailFake()
        await fake.send(Mailable(to=["user@example.com"]))
        fake.assert_sent_to("user@example.com")


class TestMailConfig:
    """NFR-038: MailSettings uses MAIL_ env prefix. SEC-021: password is SecretStr."""

    def test_defaults(self, clean_env: None) -> None:
        from arvel.mail.config import MailSettings

        settings = MailSettings()
        assert settings.driver == "log"
        assert settings.smtp_port == 587
        assert settings.smtp_use_tls is True

    def test_password_is_secret(self) -> None:
        from arvel.mail.config import MailSettings

        settings = MailSettings()
        assert "SecretStr" in type(settings.smtp_password).__name__ or hasattr(
            settings.smtp_password, "get_secret_value"
        )
