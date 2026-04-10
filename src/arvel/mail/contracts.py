"""Mail contract — ABC for swappable mail drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable


class MailContract(ABC):
    """Abstract base class for mail drivers.

    Implementations: SmtpMailer (production), LogMailer (development),
    NullMailer (dry-run).
    """

    @abstractmethod
    async def send(self, mailable: Mailable) -> None:
        """Dispatch the mailable through the configured backend.

        Raises MailSendError on transport failure.
        """
