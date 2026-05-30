"""EventServiceProvider — registers EventDispatcher and Event facade."""

from __future__ import annotations

from arvel.events.dispatcher import EventDispatcher
from arvel.providers.service_provider import ServiceProvider


class EventServiceProvider(ServiceProvider):
    """Registers the EventDispatcher singleton and wires the Event facade."""

    def register(self) -> None:
        dispatcher = EventDispatcher(container=self.container)
        self.container.instance(EventDispatcher, dispatcher)

    async def boot(self) -> None:
        from arvel.facades.event import Event

        dispatcher = self.container.make(EventDispatcher)
        Event.bind(dispatcher)


__all__ = ["EventServiceProvider"]
