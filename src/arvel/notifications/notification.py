"""Notification base class — defines multi-channel dispatch routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ShouldQueue:
    """Marker mixin — notifications implementing this are dispatched via the queue."""


@dataclass
class MailMessage:
    """Structured email content for the mail channel."""

    subject: str = ""
    body: str = ""
    template: str = ""
    context: dict[str, object] = field(default_factory=dict)


@dataclass
class DatabasePayload:
    """Structured payload for the database channel."""

    type: str = ""
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class SlackMessage:
    """Structured message for the Slack channel."""

    text: str = ""
    blocks: list[dict[str, object]] = field(default_factory=list)


class Notification:
    """Base class for notifications.

    Subclass and override ``via()`` and the ``to_*()`` methods for each channel.
    """

    def via(self) -> list[str]:
        """Return the channel names this notification should be sent to."""
        return ["mail"]

    def to_mail(self, notifiable: Any) -> MailMessage:
        """Build the mail channel representation."""
        return MailMessage()

    def to_database(self, notifiable: Any) -> DatabasePayload:
        """Build the database channel representation."""
        return DatabasePayload()

    def to_slack(self, notifiable: Any) -> SlackMessage:
        """Build the Slack channel representation."""
        return SlackMessage()
