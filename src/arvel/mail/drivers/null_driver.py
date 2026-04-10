"""NullMailer — silently discards all emails."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.mail.contracts import MailContract

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable


class NullMailer(MailContract):
    """No-op mailer — send() does nothing."""

    async def send(self, mailable: Mailable) -> None:
        pass
