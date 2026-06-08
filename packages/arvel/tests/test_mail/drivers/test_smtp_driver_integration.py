"""Real-SMTP integration tests for ``SmtpMailDriver``

The fast inner-loop suite in ``test_smtp_driver.py`` mocks the underlying
``aiosmtplib.send``. This file boots a Mailpit container, sends a real
message through aiosmtplib, then polls Mailpit's JSON inbox API
(``/api/v1/messages``) to assert the envelope arrived intact.
"""

from __future__ import annotations

import time
import urllib.request
from typing import Any, Protocol, cast

import httpx2 as httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

pytest.importorskip("aiosmtplib", reason="arvel[mail] not installed")

from arvel.mail.attachment import Attachment
from arvel.mail.config import MailEncryption, SmtpConfig
from arvel.mail.drivers.smtp import SmtpMailDriver
from arvel.mail.envelope import Envelope
from arvel.mail.exceptions import MailException
from arvel.mail.rendered_mail import RenderedMail


class MailpitEndpoint(Protocol):
    """Structural type for the ``mailpit_endpoint`` fixture (see emulators/fixtures.py)."""

    smtp_host: str
    smtp_port: int
    api_url: str


def _purge(api_url: str) -> None:
    """Delete every message Mailpit currently holds so each test starts clean."""
    req = urllib.request.Request(  # noqa: S310 - fixed scheme, controlled URL
        f"{api_url}/api/v1/messages", method="DELETE"
    )
    with urllib.request.urlopen(req, timeout=5) as response:  # noqa: S310
        assert response.status == 200


def _wait_for_message(api_url: str, subject: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Poll Mailpit's inbox until a message with ``subject`` arrives, then return it."""
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


def _rendered(subject: str, *, attachments: list[Attachment] | None = None) -> RenderedMail:
    return RenderedMail(
        envelope=Envelope(
            from_address="bot@example.com",
            to=["alice@example.com"],
            subject=subject,
            cc=["audit@example.com"],
        ),
        body_text=f"Plain body for {subject}",
        body_html=f"<p>HTML body for <strong>{subject}</strong></p>",
        attachments=attachments or [],
    )


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestSmtpDriverOps:
    @pytest_asyncio.fixture
    async def driver(
        self, mailpit_endpoint: MailpitEndpoint, monkeypatch: pytest.MonkeyPatch
    ) -> SmtpMailDriver:
        # Mailpit accepts plain SMTP on port 1025 with no auth and no TLS.
        # app.env=test suppresses the SmtpMailDriver plaintext-TLS warning.
        from types import SimpleNamespace

        from arvel.config._lookup_registry import register

        register("app", SimpleNamespace(env="test", is_production=False))
        _purge(mailpit_endpoint.api_url)
        return SmtpMailDriver(
            SmtpConfig(
                host=mailpit_endpoint.smtp_host,
                port=mailpit_endpoint.smtp_port,
                username="",
                password=SecretStr(""),
                encryption=None,
            )
        )

    async def test_send_round_trip(
        self, driver: SmtpMailDriver, mailpit_endpoint: MailpitEndpoint
    ) -> None:
        await driver.send(_rendered("Hello from Arvel"))
        msg = _wait_for_message(mailpit_endpoint.api_url, "Hello from Arvel")
        from_field = cast("dict[str, Any]", msg["From"])
        to_field = cast("list[dict[str, Any]]", msg["To"])
        cc_field = cast("list[dict[str, Any]]", msg["Cc"])
        assert from_field["Address"] == "bot@example.com"
        assert any(r["Address"] == "alice@example.com" for r in to_field)
        assert any(r["Address"] == "audit@example.com" for r in cc_field)
        text_body = cast("str", msg["Text"])
        html_body = cast("str", msg["HTML"])
        assert "Plain body for Hello from Arvel" in text_body
        assert "<strong>Hello from Arvel</strong>" in html_body

    async def test_send_with_attachment(
        self, driver: SmtpMailDriver, mailpit_endpoint: MailpitEndpoint
    ) -> None:
        attachment = Attachment(
            name="invoice.txt",
            mime="text/plain",
            data=b"INVOICE 2026-001",
        )
        await driver.send(_rendered("Invoice attached", attachments=[attachment]))
        msg = _wait_for_message(mailpit_endpoint.api_url, "Invoice attached")
        attachments = cast("list[dict[str, Any]]", msg.get("Attachments", []))
        assert len(attachments) == 1
        names = [a["FileName"] for a in attachments]
        assert "invoice.txt" in names

    async def test_send_failure_surfaces_as_mail_exception(
        self, mailpit_endpoint: MailpitEndpoint
    ) -> None:
        # Point the driver at a port nothing is listening on so aiosmtplib's
        # connect raises — verifying the driver wraps it in MailException.
        bad_driver = SmtpMailDriver(
            SmtpConfig(
                host=mailpit_endpoint.smtp_host,
                port=1,  # reserved/unused; connect will fail fast
                username="",
                password=SecretStr(""),
                encryption=MailEncryption.TLS,
            )
        )
        with pytest.raises(MailException, match="SMTP send failed"):
            await bad_driver.send(_rendered("never delivered"))
