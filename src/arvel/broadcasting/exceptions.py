"""Broadcasting exceptions."""

from __future__ import annotations


class BroadcastError(Exception):
    """Base exception for broadcasting errors."""


class ChannelAuthorizationError(BroadcastError):
    """Raised when channel authorization fails."""

    def __init__(self, channel: str, reason: str = "Unauthorized") -> None:
        self.channel = channel
        self.reason = reason
        super().__init__(f"Channel authorization failed for '{channel}': {reason}")
