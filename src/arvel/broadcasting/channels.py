"""Channel types for broadcasting — public, private, and presence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Channel:
    """Public broadcast channel. No authorization required."""

    name: str


@dataclass(frozen=True)
class PrivateChannel(Channel):
    """Private channel requiring authorization callback returning bool."""


@dataclass(frozen=True)
class PresenceChannel(Channel):
    """Presence channel returning user metadata on authorization."""
