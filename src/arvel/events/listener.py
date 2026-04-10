"""Listener base class and @queued decorator."""

from __future__ import annotations

from typing import Any, ClassVar


class Listener:
    """Base class for event listeners.

    Subclass and implement ``handle(self, event: YourEvent)``. The type
    hint on ``event`` determines which event type this listener handles.
    """

    __queued__: ClassVar[bool] = False

    async def handle(self, event: Any) -> None:
        raise NotImplementedError


def queued(cls: type[Listener]) -> type[Listener]:
    """Mark a listener for queue dispatch instead of sync execution."""
    cls.__queued__ = True
    return cls
