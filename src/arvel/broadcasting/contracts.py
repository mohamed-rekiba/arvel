"""Broadcast contract — ABC for swappable broadcast drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


class BroadcastContract(ABC):
    """Abstract base class for broadcast drivers.

    Implementations: RedisBroadcaster (production), MemoryBroadcaster (dev/test),
    LogBroadcaster (debugging), NullBroadcaster (no-op).
    """

    @abstractmethod
    async def broadcast(
        self,
        channels: list[Channel],
        event: str,
        data: dict[str, Any],
    ) -> None:
        """Push *event* with *data* to every channel in *channels*."""
