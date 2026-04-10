"""BroadcastEventListener — auto-broadcasts events implementing Broadcastable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.broadcasting.broadcastable import Broadcastable
from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.broadcasting.contracts import BroadcastContract
    from arvel.events.event import Event

logger = Log.named("arvel.broadcasting.listener")


class BroadcastEventListener:
    """Listener that broadcasts events implementing the Broadcastable protocol.

    Register with the EventDispatcher to auto-broadcast domain events.
    """

    def __init__(self, broadcaster: BroadcastContract) -> None:
        self._broadcaster = broadcaster

    async def handle(self, event: Event) -> None:
        if not isinstance(event, Broadcastable):
            return

        channels = event.broadcast_on()
        event_name = event.broadcast_as()
        data = event.broadcast_with()

        await self._broadcaster.broadcast(channels, event_name, data)
        logger.debug(
            "event_broadcast",
            event_name=event_name,
            channels=[ch.name for ch in channels],
        )
