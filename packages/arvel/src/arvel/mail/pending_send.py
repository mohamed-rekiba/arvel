"""MailPendingSend — fluent to.send chain."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable
    from arvel.mail.mailer import Mailer


class MailPendingSend:
    """Returned by ``Mailer.to()``. Call ``.send(mailable)`` to deliver."""

    def __init__(self, mailer: Mailer, address: str) -> None:
        self._mailer = mailer
        self._address = address

    async def send(self, mailable: Mailable) -> None:
        """Render and deliver the mailable."""
        await self._mailer.send_to(self._address, mailable)


__all__ = ["MailPendingSend"]
