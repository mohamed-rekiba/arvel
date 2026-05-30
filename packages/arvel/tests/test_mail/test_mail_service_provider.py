"""Tests for MailServiceProvider — FR-009-021."""

from __future__ import annotations

import pytest
from arvel import Application
from arvel.mail.mailer import Mailer
from arvel.mail.providers.mail_service_provider import MailServiceProvider


class TestMailServiceProvider:
    def test_register_binds_mailer(self) -> None:
        app = Application()
        provider = MailServiceProvider(app)
        provider.register()
        mailer = app.container.make(Mailer)
        assert isinstance(mailer, Mailer)

    @pytest.mark.asyncio
    async def test_boot_binds_mail_facade(self) -> None:
        from arvel.facades.mail import Mail

        app = Application()
        provider = MailServiceProvider(app)
        provider.register()
        await provider.boot()
        assert Mail.get_mailer() is not None
