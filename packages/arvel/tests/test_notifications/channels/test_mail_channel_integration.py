"""Real-SMTP integration test for ``MailChannel`` — FR-009-025.

The fast inner-loop suite in ``test_mail_channel.py`` uses ``ArrayMailDriver``.
This file wires a real ``Mailer`` around ``SmtpMailDriver`` pointed at a
Mailpit container and verifies a notification's mailable actually traverses
the SMTP wire and lands in Mailpit's inbox.
"""

from __future__ import annotations

import time
import urllib.request
from typing import Any, Protocol, cast

import httpx
import pytest
import pytest_asyncio
from arvel.mail.config import MailConfig, SmtpConfig
from arvel.mail.content import Content
from arvel.mail.drivers.smtp import SmtpMailDriver
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable
from arvel.mail.mailer import Mailer
from arvel.notifications.channels.mail_channel import MailChannel
from arvel.notifications.notification import Notification
from pydantic import SecretStr

pytest.importorskip("aiosmtplib", reason="arvel[mail] not installed")


class MailpitEndpoint(Protocol):
    """Structural type for the ``mailpit_endpoint`` fixture (see emulators/fixtures.py)."""

    smtp_host: str
    smtp_port: int
    api_url: str


def _purge(api_url: str) -> None:
    req = urllib.request.Request(  # noqa: S310 - fixed scheme, controlled URL
        f"{api_url}/api/v1/messages", method="DELETE"
    )
    with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
        assert response.status == 200


def _wait_for_message(api_url: str, subject: str, *, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with httpx.Client(timeout=2.0) as client:
            inbox: Any = client.get(f"{api_url}/api/v1/messages").json()
        entries = cast("list[dict[str, Any]]", inbox.get("messages", []))
        for entry in entries:
            if entry.get("Subject") == subject:
                msg_id = entry["ID"]
                with httpx.Client(timeout=2.0) as client:
                    return cast(
                        "dict[str, Any]",
                        client.get(f"{api_url}/api/v1/message/{msg_id}").json(),
                    )
        time.sleep(0.1)
    pytest.fail(f"Mailpit never received a message with subject {subject!r}")


class _FakeUser:
    def __init__(self, user_id: int, email: str) -> None:
        self.id = user_id
        self.email = email


class _WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(
            from_address="no-reply@example.com",
            to=["placeholder@example.com"],  # MailChannel rewrites via override_to
            subject="Welcome (live)",
        )

    def content(self) -> Content:
        return Content(text="Welcome to Arvel — this message went through real SMTP.")


class _WelcomeNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["mail"]

    def to_mail(self, notifiable: Any) -> Mailable:
        return _WelcomeMail()


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestMailChannelOps:
    @pytest_asyncio.fixture
    async def channel(
        self, mailpit_endpoint: MailpitEndpoint, monkeypatch: pytest.MonkeyPatch
    ) -> MailChannel:
        # app.env=test silences the SmtpMailDriver's plaintext-TLS warning.
        from types import SimpleNamespace

        from arvel.config._lookup_registry import register

        register("app", SimpleNamespace(env="test", is_production=False))
        _purge(mailpit_endpoint.api_url)
        driver = SmtpMailDriver(
            SmtpConfig(
                host=mailpit_endpoint.smtp_host,
                port=mailpit_endpoint.smtp_port,
                username="",
                password=SecretStr(""),
                encryption=None,
            )
        )
        mailer = Mailer(default_driver=driver, config=MailConfig(default="smtp"))
        return MailChannel(mailer)

    async def test_send_routes_through_smtp(
        self, channel: MailChannel, mailpit_endpoint: MailpitEndpoint
    ) -> None:
        await channel.send(_FakeUser(1, "alice@example.com"), _WelcomeNotification())
        msg = _wait_for_message(mailpit_endpoint.api_url, "Welcome (live)")
        to_field = cast("list[dict[str, Any]]", msg["To"])
        assert any(r["Address"] == "alice@example.com" for r in to_field)
        text_body = cast("str", msg["Text"])
        assert "real SMTP" in text_body
