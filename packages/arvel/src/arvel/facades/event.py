"""Event facade — classmethod API proxying to the bound EventDispatcher."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol, TypeVar

from arvel.queue.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.events.event import Event as _Event
    from arvel.testing.fakes.event import EventFakeContext

_E = TypeVar("_E", bound="_Event")


class EventDispatcherLike(Protocol):
    """Minimal surface the Event facade needs from its bound dispatcher.

    Implemented by ``arvel.events.dispatcher.EventDispatcher`` (production)
    and ``arvel.testing.fakes.event.EventFake`` (tests).
    """

    async def dispatch(self, event: _Event) -> None: ...


class Event:
    """Facade providing classmethod dispatch API for the events subsystem.

    Bound by ``EventServiceProvider.boot()``.
    """

    dispatcher: ClassVar[EventDispatcherLike | None] = None

    @classmethod
    def bind(cls, dispatcher: EventDispatcherLike) -> None:
        cls.dispatcher = dispatcher

    @classmethod
    def swap_dispatcher(cls, new: EventDispatcherLike | None) -> EventDispatcherLike | None:
        """Replace the bound dispatcher and return the previous one. Test-only."""
        previous = cls.dispatcher
        cls.dispatcher = new
        return previous

    @classmethod
    def _get_dispatcher(cls) -> EventDispatcherLike:
        if cls.dispatcher is None:
            raise FacadeNotBoundError("Event")
        return cls.dispatcher

    @classmethod
    async def dispatch(cls, event: _Event) -> None:
        await cls._get_dispatcher().dispatch(event)

    @classmethod
    def fake(cls) -> EventFakeContext:
        """Swap in an EventFake recorder for tests."""
        from arvel.testing.fakes.event import EventFakeContext

        return EventFakeContext()

    @classmethod
    def assert_dispatched(cls, event_class: type[_E], times: int | None = None) -> None:
        """Assert that an event of ``event_class`` was dispatched (test-only)."""
        from arvel.testing.fakes.event import EventFake

        dispatcher = cls.dispatcher
        if not isinstance(dispatcher, EventFake):
            raise AssertionError("Event.assert_dispatched requires Event.fake() context")
        matching = dispatcher.dispatched_of(event_class)
        if not matching:
            raise AssertionError(f"Event {event_class.__name__!r} was not dispatched")
        if times is not None and len(matching) != times:
            raise AssertionError(
                f"Event {event_class.__name__!r}: expected {times} dispatches, got {len(matching)}"
            )

    @classmethod
    def assert_not_dispatched(cls, event_class: type[_E]) -> None:
        """Assert that NO event of ``event_class`` was dispatched."""
        from arvel.testing.fakes.event import EventFake

        dispatcher = cls.dispatcher
        if not isinstance(dispatcher, EventFake):
            raise AssertionError("Event.assert_not_dispatched requires Event.fake() context")
        matching = dispatcher.dispatched_of(event_class)
        if matching:
            raise AssertionError(
                f"Event {event_class.__name__!r} was dispatched {len(matching)} time(s)"
            )


__all__ = ["Event", "EventDispatcherLike"]
