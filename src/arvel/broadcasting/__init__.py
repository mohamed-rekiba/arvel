"""arvel.broadcasting — broadcast ``ShouldBroadcast`` events to realtime channels.

The event dispatcher routes a ``ShouldBroadcast`` event to the bound ``broadcast`` manager,
which sends it on the event's channels. Core ships a ``log`` driver (records, no network) for
dev/test; the realtime transports (Pusher/Ably/websocket/Redis) are driver extras. Grounded in
knowledge/port/11-events.md.
"""

from __future__ import annotations

from typing import Any, cast

from arvel.kernel import Settings
from arvel.support.manager import Manager


class BroadcastingSettings(Settings):
    """Typed, validated view over the ``broadcasting`` config section (DR-0016)."""

    __config_key__ = "broadcasting"
    default: str = "log"  # driver name (open registry → str)


def channels_for(event: Any) -> list[str]:
    """The channel names an event broadcasts on (its ``broadcast_on()``), or ``[]``."""
    getter = getattr(event, "broadcast_on", None)
    if not callable(getter):
        return []
    return [str(c) for c in cast("list[Any]", getter())]


def event_name(event: Any) -> str:
    """The wire name for an event (its ``broadcast_as()``, else the class name)."""
    getter = getattr(event, "broadcast_as", None)
    return str(getter()) if callable(getter) else type(event).__name__


class Broadcaster:
    """Base broadcaster: override ``broadcast``."""

    async def broadcast(self, event: Any) -> None:
        raise NotImplementedError


class LogBroadcaster(Broadcaster):
    """A no-network broadcaster that records each broadcast (dev/test default)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str], Any]] = []

    async def broadcast(self, event: Any) -> None:
        self.sent.append((event_name(event), channels_for(event), event))


class BroadcastManager(Manager):
    """Resolves broadcast drivers by config and sends events to the active one."""

    def default_driver(self) -> str:
        return BroadcastingSettings().default  # auto-loads + validates config("broadcasting")

    def create_log_driver(self) -> LogBroadcaster:
        return LogBroadcaster()

    async def broadcast(self, event: Any) -> None:
        await self.driver().broadcast(event)


__all__ = [
    "BroadcastManager",
    "Broadcaster",
    "BroadcastingSettings",
    "LogBroadcaster",
    "channels_for",
    "event_name",
]
