"""Listener[E] generic abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from arvel.events.event import Event

E = TypeVar("E", bound=Event)


class Listener(ABC, Generic[E]):
    """Base class for all event listeners.

    Subclasses implement ``handle(event: E) -> None``.
    Auto-registers concrete (non-abstract) subclasses in ListenerRegistry
    so ListenerJob can safely deserialize them.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from arvel.events.listener_registry import ListenerRegistry

        key = f"{cls.__module__}.{cls.__qualname__}"
        ListenerRegistry[key] = cls

    @abstractmethod
    async def handle(self, event: E) -> None:
        """React to an event."""


__all__ = ["Listener"]
