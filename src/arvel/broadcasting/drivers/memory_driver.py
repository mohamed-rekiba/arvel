"""MemoryBroadcaster — in-process driver that stores broadcasts for retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.broadcasting.contracts import BroadcastContract

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


class MemoryBroadcaster(BroadcastContract):
    """Stores broadcasts in-memory for inspection during development and testing."""

    def __init__(self) -> None:
        self._broadcasts: list[dict[str, Any]] = []

    @property
    def broadcasts(self) -> list[dict[str, Any]]:
        return list(self._broadcasts)

    async def broadcast(
        self,
        channels: list[Channel],
        event: str,
        data: dict[str, Any],
    ) -> None:
        self._broadcasts.append(
            {
                "channels": [ch.name for ch in channels],
                "event": event,
                "data": data,
            }
        )

    def flush(self) -> None:
        """Clear all recorded broadcasts."""
        self._broadcasts.clear()
