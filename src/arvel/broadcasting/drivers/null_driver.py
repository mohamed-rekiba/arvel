"""NullBroadcaster — no-op driver for environments without broadcasting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.broadcasting.contracts import BroadcastContract

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


class NullBroadcaster(BroadcastContract):
    """Discards all broadcasts. Use in test/CLI environments."""

    async def broadcast(
        self,
        channels: list[Channel],
        event: str,
        data: dict[str, Any],
    ) -> None:
        pass
