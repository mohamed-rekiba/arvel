"""Tests for LogMailDriver."""

from __future__ import annotations

import pytest
from arvel.mail.content import Content
from arvel.mail.drivers.log import LogMailDriver
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable
from arvel.mail.rendered_mail import RenderedMail


class _WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(from_address="a@b.com", to=["c@d.com"], subject="Welcome, Alice!")

    def content(self) -> Content:
        return Content(text="body")


class TestLogMailDriver:
    @pytest.mark.asyncio
    async def test_send_never_raises(self) -> None:
        driver = LogMailDriver()
        rendered = RenderedMail(
            envelope=_WelcomeMail().envelope(),
            body_text="body",
            body_html=None,
            attachments=[],
        )
        await driver.send(rendered)  # must not raise

    @pytest.mark.asyncio
    async def test_send_logs_envelope_subject(self) -> None:
        """log driver emits envelope details."""
        from arvel.testing.observability import FakeObservability

        driver = LogMailDriver()
        rendered = RenderedMail(
            envelope=_WelcomeMail().envelope(),
            body_text="body",
            body_html=None,
            attachments=[],
        )
        with FakeObservability() as obs:
            await driver.send(rendered)

        assert any(r.body == "mail_sent" for r in obs.log_records), (
            "Log driver must emit mail_sent event"
        )
