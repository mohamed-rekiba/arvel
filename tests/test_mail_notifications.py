"""Phase 6 — Mail (aiosmtplib) + Notifications (apprise) managers."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.mail import LogTransport, Mailable, MailManager
from arvel.notifications import Notifiable, Notification, NotificationManager
from arvel.support.manager import MissingExtraError


class WelcomeMail(Mailable):
    def build(self) -> Mailable:
        return self.subject("Welcome").html("<p>Hi</p>")


async def test_mail_log_transport_records_message() -> None:
    mailer = MailManager()  # default 'log'
    assert mailer.default_driver() == "log"
    await mailer.to("ada@example.com").send(WelcomeMail())
    transport = mailer.transport()
    assert isinstance(transport, LogTransport)
    assert len(transport.sent) == 1
    sent = transport.sent[0]
    assert sent["Subject"] == "Welcome"
    assert sent["To"] == "ada@example.com"


def test_mail_missing_driver_raises() -> None:
    with pytest.raises(MissingExtraError):
        MailManager().driver("postmark")


class WelcomeNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable: Any) -> Mailable:
        return WelcomeMail()

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"message": "welcome"}


async def test_notification_fans_out_to_channels() -> None:
    manager = NotificationManager()
    results = await manager.send("ada@example.com", WelcomeNotification())
    assert set(results) == {"mail", "database"}
    assert results["mail"] is True
    assert results["database"] == {"message": "welcome"}


async def test_notifiable_mixin() -> None:
    class User(Notifiable):
        email = "bob@example.com"

    results = await User().notify(WelcomeNotification())
    assert results["database"] == {"message": "welcome"}
