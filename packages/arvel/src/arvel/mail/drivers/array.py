"""ArrayMailDriver — in-memory driver for testing."""

from __future__ import annotations

from arvel.mail.rendered_mail import RenderedMail


class ArrayMailDriver:
    """Captures sent mail in-memory. Never raises.

    Use ``Mail.fake`` to swap the active driver in tests.
    """

    def __init__(self) -> None:
        self.sent: list[RenderedMail] = []

    async def send(self, mail: RenderedMail) -> None:
        self.sent.append(mail)

    def reset(self) -> None:
        """Clear the sent list between test assertions."""
        self.sent.clear()


__all__ = ["ArrayMailDriver"]
