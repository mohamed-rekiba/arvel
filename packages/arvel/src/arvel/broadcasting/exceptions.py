"""Broadcasting subsystem exceptions (FR-013-013)."""

from __future__ import annotations


class BroadcastException(Exception):
    """Base class for every broadcasting-side exception."""


class BroadcastDriverError(BroadcastException):
    """Raised when a broadcast driver fails (network, serialization, missing extra)."""


class BroadcastChannelError(BroadcastException):
    """Raised when a channel name is invalid or unsupported."""


class BroadcastAuthError(BroadcastException):
    """Raised when channel authorization fails."""


__all__ = [
    "BroadcastAuthError",
    "BroadcastChannelError",
    "BroadcastDriverError",
    "BroadcastException",
]
