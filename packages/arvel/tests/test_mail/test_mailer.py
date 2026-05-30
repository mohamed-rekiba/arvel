"""Tests for Mailer and MailPendingSend — FR-009-015, FR-009-016, FR-009-020."""

from __future__ import annotations

import pytest
from arvel.mail.config import MailConfig
from arvel.mail.drivers.array import ArrayMailDriver
from arvel.mail.mailer import Mailer

from .helpers import OrderMail, WelcomeMail


class TestMailer:
    def _make_mailer(self) -> tuple[Mailer, ArrayMailDriver]:
        driver = ArrayMailDriver()
        config = MailConfig(default="array")
        mailer = Mailer(default_driver=driver, config=config)
        return mailer, driver

    @pytest.mark.asyncio
    async def test_to_returns_pending_send(self) -> None:
        from arvel.mail.pending_send import MailPendingSend

        mailer, _ = self._make_mailer()
        pending = mailer.to("x@y.com")
        assert isinstance(pending, MailPendingSend)

    @pytest.mark.asyncio
    async def test_send_routes_to_driver(self) -> None:
        mailer, driver = self._make_mailer()
        await mailer.to("user@example.com").send(WelcomeMail("Alice"))
        assert len(driver.sent) == 1

    @pytest.mark.asyncio
    async def test_sent_mail_has_correct_envelope(self) -> None:
        mailer, driver = self._make_mailer()
        await mailer.to("user@example.com").send(WelcomeMail("Alice"))
        sent = driver.sent[0]
        assert sent.envelope.subject == "Welcome, Alice!"

    @pytest.mark.asyncio
    async def test_send_order_with_attachment(self) -> None:
        mailer, driver = self._make_mailer()
        await mailer.to("customer@example.com").send(OrderMail(123))
        sent = driver.sent[0]
        assert len(sent.attachments) == 1
        assert sent.attachments[0].name == "invoice.pdf"

    @pytest.mark.asyncio
    async def test_to_accepts_object_with_email_attr(self) -> None:
        class User:
            email = "user@example.com"

        mailer, driver = self._make_mailer()
        await mailer.to(User()).send(WelcomeMail("Bob"))
        assert len(driver.sent) == 1


class TestMailFake:
    """FR-009-020: Mail.fake() returns array driver and works as context manager."""

    def setup_method(self) -> None:
        from arvel.facades.mail import Mail
        from arvel.mail.config import MailConfig
        from arvel.mail.drivers.array import ArrayMailDriver
        from arvel.mail.mailer import Mailer

        mailer = Mailer(default_driver=ArrayMailDriver(), config=MailConfig(default="array"))
        Mail.bind(mailer)

    def teardown_method(self) -> None:
        from arvel.facades.mail import Mail

        Mail.reset()

    def test_fake_returns_array_driver(self) -> None:
        from arvel.facades.mail import Mail

        driver = Mail.fake()
        # fake() returns a _FakeContext that wraps ArrayMailDriver
        # it exposes .sent and .reset() and works as a context manager
        assert hasattr(driver, "sent")
        assert isinstance(driver.sent, list)

    @pytest.mark.asyncio
    async def test_fake_context_reset_clears_sent_mail(self) -> None:
        from arvel.facades.mail import Mail

        driver = Mail.fake()
        await Mail.to("x@y.com").send(WelcomeMail("Reset"))
        driver.reset()
        assert driver.sent == []

    @pytest.mark.asyncio
    async def test_fake_driver_captures_sent_mail(self) -> None:
        from arvel.facades.mail import Mail

        driver = Mail.fake()
        await Mail.to("x@y.com").send(WelcomeMail("Test"))
        assert len(driver.sent) == 1

    @pytest.mark.asyncio
    async def test_fake_context_manager_restores_original_driver(self) -> None:
        """NFR-009-010: Mail.fake() as context manager."""
        from arvel.facades.mail import Mail

        original_driver = Mail.get_mailer().current_driver
        with Mail.fake() as driver:
            await Mail.to("x@y.com").send(WelcomeMail("CM"))
            assert len(driver.sent) == 1
        assert Mail.get_mailer().current_driver is original_driver
