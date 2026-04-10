"""EventDispatcher contract — protocol for event dispatch implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from arvel.events.event import Event
    from arvel.events.listener import Listener


class EventDispatcherContract(Protocol):
    """Protocol defining the event dispatcher interface."""

    async def dispatch(self, event: Event) -> None:
        """Dispatch an event to all registered listeners."""
        ...

    def register(
        self,
        event_type: type[Event],
        listener_class: type[Listener],
        *,
        priority: int = 50,
    ) -> None:
        """Register a listener class for an event type."""
        ...

    def listeners_for(self, event_type: type[Event]) -> list[type[Listener]]:
        """Return all listener classes registered for an event type."""
        ...
