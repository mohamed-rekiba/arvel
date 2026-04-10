"""EventDispatcher — dispatches domain events to registered listeners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.events.event import Event
    from arvel.events.listener import Listener

logger = Log.named("arvel.events.dispatcher")


class _Registration:
    __slots__ = ("listener_class", "priority")

    def __init__(self, listener_class: type[Listener], priority: int) -> None:
        self.listener_class = listener_class
        self.priority = priority


class EventDispatcher:
    """In-process event dispatcher with sync and queued listener support."""

    def __init__(self) -> None:
        self._registry: dict[type[Event], list[_Registration]] = {}

    def register(
        self,
        event_type: type[Event],
        listener_class: type[Listener],
        *,
        priority: int = 50,
    ) -> None:
        """Register a listener class for an event type with optional priority."""
        registrations = self._registry.setdefault(event_type, [])
        registrations.append(_Registration(listener_class, priority))
        registrations.sort(key=lambda r: r.priority)

    def listeners_for(self, event_type: type[Event]) -> list[type[Listener]]:
        """Return listener classes registered for an event type, sorted by priority."""
        return [r.listener_class for r in self._registry.get(event_type, [])]

    async def dispatch(self, event: Event) -> None:
        """Dispatch an event to all registered listeners.

        Sync listeners execute inline. Queued listeners are skipped here
        (a real integration would dispatch them via QueueContract).
        """
        registrations = self._registry.get(type(event), [])
        for reg in registrations:
            if getattr(reg.listener_class, "__queued__", False):
                logger.debug(
                    "Skipping queued listener %s (would dispatch to queue)",
                    reg.listener_class.__name__,
                )
                continue
            listener = reg.listener_class()
            await listener.handle(event)
