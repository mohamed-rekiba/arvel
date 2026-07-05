"""Integration (spec 19 §2) — mail deliverability through a real app boot + send: no SMTP-capture
fixture is wired for this kit (grepped `tests/integration/conftest.py` — none), so this exercises
the ``log`` driver end to end and asserts the captured message carries both MIME parts (the
themed markdown HTML + its readable text alternative)."""

from __future__ import annotations

import pytest

from arvel import Application, Mail
from arvel.kernel import set_application
from arvel.kernel.bootstrap import bootstrap_app
from arvel.mail import Mailable

pytestmark = pytest.mark.integration


class Receipt(Mailable):
    def build(self) -> Mailable:
        return self.subject("Receipt").markdown(
            "Thanks for your order!\n\n[button: View Order](https://arvel.test/o/1)"
        )


async def test_markdown_mail_send_captures_both_mime_parts_through_a_real_app_boot() -> None:
    app = (
        Application.configure(".")
        .with_config(
            {
                "app": {"key": "base64:" + "A" * 43 + "=", "url": "http://test"},
                "mail": {"default": "log"},
            }
        )
        .create()
    )
    try:
        bootstrap_app(app)
        await app.boot()

        await Mail.to("ada@example.com").send(Receipt())

        sent = app.make("mail").transport().sent
        assert len(sent) == 1
        message = sent[0]

        assert message.get_content_type() == "multipart/alternative"
        assert {p.get_content_type() for p in message.iter_parts()} == {"text/plain", "text/html"}

        html_body = message.get_body(preferencelist=("html",))
        assert html_body is not None
        assert "border-radius" in html_body.get_content()  # the theme's styled button

        text_body = message.get_body(preferencelist=("plain",))
        assert text_body is not None
        text = text_body.get_content()
        assert "View Order" in text
        assert "<" not in text  # no leaked HTML in the plain-text alternative
    finally:
        set_application(None)
