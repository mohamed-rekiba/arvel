"""EventFake + Event.fake/.assert_* —"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Self, TypeVar

from arvel.events.event import Event as _Event

if TYPE_CHECKING:
    from arvel.facades.event import EventDispatcherLike

_E = TypeVar("_E", bound=_Event)


@dataclass
class EventFake:
    """In-memory event dispatcher — records every dispatched event."""

    dispatched: list[_Event] = field(default_factory=list[_Event])

    async def dispatch(self, event: _Event) -> None:
        self.dispatched.append(event)

    def dispatched_of(self, event_class: type[_E]) -> list[_E]:
        return [e for e in self.dispatched if isinstance(e, event_class)]


class EventFakeContext:
    """Context manager: swap the bound EventDispatcher with an EventFake."""

    def __init__(self) -> None:
        self._original: EventDispatcherLike | None = None
        self.fake = EventFake()

    def __enter__(self) -> Self:
        from arvel.facades.event import Event

        self._original = Event.swap_dispatcher(self.fake)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        from arvel.facades.event import Event

        Event.swap_dispatcher(self._original)


__all__ = ["EventFake", "EventFakeContext"]
