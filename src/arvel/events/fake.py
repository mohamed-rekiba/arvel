"""EventFake — testing double for EventDispatcherContract."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.events.event import Event


class EventFake:
    """Captures dispatched events for test assertions.

    Use in tests to replace the real EventDispatcher and verify
    that events were dispatched without executing listeners.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []

    @property
    def dispatched_count(self) -> int:
        return len(self._events)

    async def dispatch(self, event: Event) -> None:
        self._events.append(event)

    def assert_dispatched(
        self,
        event_type: type[Event],
        predicate: Callable[[Event], bool] | None = None,
    ) -> None:
        matches = [e for e in self._events if isinstance(e, event_type)]
        if not matches:
            msg = f"Expected {event_type.__name__} to be dispatched, but it wasn't"
            raise AssertionError(msg)
        if predicate is not None and not any(predicate(m) for m in matches):
            msg = (
                f"Expected {event_type.__name__} matching predicate to be dispatched, "
                f"but none of the {len(matches)} dispatched event(s) matched"
            )
            raise AssertionError(msg)

    def assert_not_dispatched(self, event_type: type[Event]) -> None:
        matches = [e for e in self._events if isinstance(e, event_type)]
        if matches:
            msg = (
                f"Expected {event_type.__name__} not to be dispatched, "
                f"but it was ({len(matches)} time(s))"
            )
            raise AssertionError(msg)

    def assert_dispatched_count(self, event_type: type[Event], expected: int) -> None:
        actual = len([e for e in self._events if isinstance(e, event_type)])
        if actual != expected:
            msg = f"Expected {expected} {event_type.__name__} events, but got {actual}"
            raise AssertionError(msg)

    def assert_nothing_dispatched(self) -> None:
        if self._events:
            types = {type(e).__name__ for e in self._events}
            msg = f"Expected no events dispatched, but got {len(self._events)}: {types}"
            raise AssertionError(msg)
