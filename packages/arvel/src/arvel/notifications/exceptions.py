"""Notifications subsystem exceptions."""

from __future__ import annotations


class NotificationException(Exception):
    """Base notifications exception."""


class UnknownChannelError(NotificationException):
    """Raised when a channel name is not registered in NotificationManager."""

    def __init__(self, channel: str) -> None:
        super().__init__(
            f"Unknown notification channel: {channel!r}. Register the channel before dispatching."
        )


__all__ = ["NotificationException", "UnknownChannelError"]
