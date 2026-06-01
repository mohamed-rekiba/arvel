"""ListenerJob — bridges ShouldQueue listener dispatch to the queue."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.queue.job import Job

if TYPE_CHECKING:
    from arvel.events.event import Event
    from arvel.events.listener import Listener


class ListenerJob(Job):
    """Queued job that carries a serialized event and executes a Listener.

    Created by EventDispatcher when a listener implements ShouldQueue.
    Uses EventRegistry and JobRegistry allowlists for safe deserialization.
    """

    listener_class_key: str
    event_class_key: str
    event_json: str

    @classmethod
    def create(cls, listener_cls: type[Listener[Any]], event: Event) -> ListenerJob:
        """Factory — construct from a concrete listener class and event instance."""
        return cls(
            listener_class_key=f"{listener_cls.__module__}.{listener_cls.__qualname__}",
            event_class_key=f"{type(event).__module__}.{type(event).__qualname__}",
            event_json=event.model_dump_json(),
        )

    async def handle(self) -> None:
        from arvel.events.event import EventRegistry
        from arvel.events.listener_registry import ListenerRegistry

        listener_cls = ListenerRegistry[self.listener_class_key]
        event_cls = EventRegistry[self.event_class_key]
        event = event_cls.model_validate_json(self.event_json)
        listener = self._resolve_listener(listener_cls)
        await listener.handle(event)

    def _resolve_listener(self, listener_cls: type[Listener[Any]]) -> Listener[Any]:
        from arvel.events.dispatcher import EventDispatcher
        from arvel.facades.event import Event

        dispatcher = Event.dispatcher
        if isinstance(dispatcher, EventDispatcher):
            return dispatcher.resolve_listener(listener_cls)
        return listener_cls()


__all__ = ["ListenerJob"]
