"""Tests for ArrayMailDriver — FR-009-018."""

from __future__ import annotations

import pytest
from arvel.mail.content import Content
from arvel.mail.drivers.array import ArrayMailDriver
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable
from arvel.mail.rendered_mail import RenderedMail


class _WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(from_address="a@b.com", to=["c@d.com"], subject="Welcome, Test!")

    def content(self) -> Content:
        return Content(text="Welcome")


class TestArrayMailDriver:
    @pytest.mark.asyncio
    async def test_send_appends_to_sent(self) -> None:
        driver = ArrayMailDriver()
        mailable = _WelcomeMail()
        rendered = RenderedMail(
            envelope=mailable.envelope(),
            body_text="Welcome",
            body_html=None,
            attachments=mailable.attachments(),
        )
        await driver.send(rendered)
        assert len(driver.sent) == 1
        assert driver.sent[0] is rendered

    @pytest.mark.asyncio
    async def test_send_never_raises(self) -> None:
        driver = ArrayMailDriver()
        bad_mail = RenderedMail(
            envelope=_WelcomeMail().envelope(),
            body_text="",
            body_html=None,
            attachments=[],
        )
        await driver.send(bad_mail)  # should not raise

    def test_reset_clears_sent(self) -> None:
        driver = ArrayMailDriver()
        driver.sent.append(
            RenderedMail(
                envelope=_WelcomeMail().envelope(),
                body_text="",
                body_html=None,
                attachments=[],
            )
        )
        driver.reset()
        assert driver.sent == []
