"""Tests for MailChannel — FR-009-025."""

from __future__ import annotations

import pytest
from arvel.mail.config import MailConfig
from arvel.mail.drivers.array import ArrayMailDriver
from arvel.mail.mailer import Mailer
from arvel.notifications.channels.mail_channel import MailChannel

from test_notifications.helpers import (  # type: ignore[import-not-found]
    DbOnlyNotification,
    FakeUser,
    WelcomeNotification,
)


class TestMailChannel:
    def _channel(self) -> tuple[MailChannel, ArrayMailDriver]:
        driver = ArrayMailDriver()
        mailer = Mailer(default_driver=driver, config=MailConfig(default="array"))
        return MailChannel(mailer), driver

    @pytest.mark.asyncio
    async def test_sends_mailable_when_to_mail_returns_one(self) -> None:
        channel, driver = self._channel()
        await channel.send(FakeUser(1), WelcomeNotification())
        assert len(driver.sent) == 1

    @pytest.mark.asyncio
    async def test_skips_silently_when_to_mail_returns_none(self) -> None:
        """FR-009-025: silently skips if to_mail() returns None."""
        channel, driver = self._channel()
        await channel.send(FakeUser(1), DbOnlyNotification())
        assert len(driver.sent) == 0
