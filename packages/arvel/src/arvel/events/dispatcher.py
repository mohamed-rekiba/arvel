"""EventDispatcher — registry + dispatch logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.events.event import Event
from arvel.events.should_queue import ShouldQueue
from arvel.logging.facade import Log

if TYPE_CHECKING:
    from arvel.container.container import Container
    from arvel.events.listener import Listener

logger = Log.channel(__name__)


class EventDispatcher:
    """In-process synchronous event dispatcher.

    Listeners registered via ``listen`` are called in registration order.
    Listeners that implement ShouldQueue are dispatched via Bus.
    Per-listener errors are caught and logged; remaining listeners still run.
    """

    def __init__(self, container: Container | None = None) -> None:
        self._registry: dict[type[Event], list[type[Listener[Any]]]] = {}
        self._container = container

    def listen(self, event_cls: type[Event], listener_cls: type[Listener[Any]]) -> None:
        """Register a listener for an event class. Idempotent."""
        bucket = self._registry.setdefault(event_cls, [])
        if listener_cls not in bucket:
            bucket.append(listener_cls)

    def listeners(self, event_cls: type[Event]) -> list[type[Listener[Any]]]:
        """Return the registered listeners for the given event class."""
        return list(self._registry.get(event_cls, []))

    def resolve_listener(self, listener_cls: type[Listener[Any]]) -> Listener[Any]:
        """Instantiate a listener through DI when the dispatcher has a container."""
        if self._container is not None:
            return self._container.make(listener_cls)
        return listener_cls()

    def all_listeners(self) -> dict[type[Event], list[type[Listener[Any]]]]:
        """Return a snapshot of the full event-to-listeners registry."""
        return {event_cls: list(listeners) for event_cls, listeners in self._registry.items()}

    async def dispatch(self, event: Event) -> None:
        """Dispatch event to all registered listeners.

        If the event also mixes in ``ShouldBroadcast``, route it through the
        Broadcast facade after sync listeners finish.
        """
        listeners = self._registry.get(type(event), [])
        for listener_cls in listeners:
            if issubclass(listener_cls, ShouldQueue):
                await self._dispatch_queued(listener_cls, event)
            else:
                await self._dispatch_inline(listener_cls, event)
        await self._maybe_broadcast(event)

    async def _maybe_broadcast(self, event: Event) -> None:
        from arvel.broadcasting.should_broadcast import ShouldBroadcast

        if not isinstance(event, ShouldBroadcast):
            return
        try:
            from arvel.facades.broadcast import Broadcast

            if Broadcast.manager is None:
                return
            await Broadcast.event(event)
        except Exception:
            logger.exception(
                "broadcast_dispatch_error",
                event_type=type(event).__name__,
            )

    async def _dispatch_inline(self, listener_cls: type[Listener[Any]], event: Event) -> None:
        try:
            listener = self.resolve_listener(listener_cls)
            await listener.handle(event)
        except Exception:
            logger.exception(
                "listener_error",
                listener=f"{listener_cls.__module__}.{listener_cls.__qualname__}",
                event_type=type(event).__name__,
            )

    async def _dispatch_queued(self, listener_cls: type[Listener[Any]], event: Event) -> None:
        """Enqueue via Bus; fall back to inline if Bus is not bound."""
        from arvel.events.listener_job import ListenerJob

        try:
            from arvel.facades.bus import Bus  # lazy import to avoid circular dep

            if Bus.manager is not None:
                job = ListenerJob.create(listener_cls=listener_cls, event=event)
                await Bus.dispatch(job)
                return
        except Exception:
            # Logged upstream; a Bus failure must not break the publish loop.
            pass  # nosec B110

        logger.debug(
            "shouldqueue_fallback_inline",
            listener=f"{listener_cls.__module__}.{listener_cls.__qualname__}",
        )
        await self._dispatch_inline(listener_cls, event)


__all__ = ["EventDispatcher"]
