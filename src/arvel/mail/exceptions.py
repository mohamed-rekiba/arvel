"""Mail exceptions."""

from __future__ import annotations


class MailError(Exception):
    """Base exception for mail operations."""


class MailSendError(MailError):
    """Raised when the mail transport fails to deliver.

    Attributes:
        recipient: Primary recipient address (for diagnostics).
        driver: Name of the driver that failed.
    """

    def __init__(self, recipient: str, driver: str, detail: str = "") -> None:
        self.recipient = recipient
        self.driver = driver
        msg = f"Failed to send email to '{recipient}' via {driver} driver"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
