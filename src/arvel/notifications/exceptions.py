"""Notification exceptions."""

from __future__ import annotations


class NotificationError(Exception):
    """Base exception for notification operations."""


class NotificationChannelError(NotificationError):
    """Raised when a specific channel fails to deliver.

    Attributes:
        channel: Name of the channel that failed.
    """

    def __init__(self, channel: str, detail: str = "") -> None:
        self.channel = channel
        msg = f"Notification delivery failed on '{channel}' channel"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
