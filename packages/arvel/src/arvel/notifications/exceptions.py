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


class UnregisteredNotificationClassError(NotificationException):
    """Raised when a queued job references a class missing from the allowlist registry.

    Queued NotificationJobs resolve the notifiable and notification classes from
    registries populated at class-definition time — never by importing the dotted
    path from the (untrusted) queue payload. A miss means the class wasn't loaded
    (worker is missing the module) or the payload was tampered with.
    """

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(
            f"Unregistered {kind} class {key!r}: not found in the notifications allowlist. "
            f"Make sure the worker imports the module that defines it."
        )


__all__ = [
    "NotificationException",
    "UnknownChannelError",
    "UnregisteredNotificationClassError",
]
