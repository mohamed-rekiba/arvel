"""Shared fixtures for mail tests."""

from __future__ import annotations

from arvel.mail.attachment import Attachment
from arvel.mail.content import Content
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable


class WelcomeMail(Mailable):
    def __init__(self, name: str) -> None:
        self.name = name

    def envelope(self) -> Envelope:
        return Envelope(
            from_address="no-reply@example.com",
            to=["user@example.com"],
            subject=f"Welcome, {self.name}!",
        )

    def content(self) -> Content:
        return Content(text=f"# Hello {self.name}\n\nThank you for joining.")


class OrderMail(Mailable):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id

    def envelope(self) -> Envelope:
        return Envelope(
            from_address="orders@example.com",
            to=["customer@example.com"],
            subject=f"Order #{self.order_id} shipped",
        )

    def content(self) -> Content:
        return Content(text=f"Your order #{self.order_id} is on its way.")

    def attachments(self) -> list[Attachment]:
        return [Attachment(data=b"PDF", name="invoice.pdf", mime="application/pdf")]
