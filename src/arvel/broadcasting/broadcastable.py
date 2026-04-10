"""Broadcastable protocol — events implement this to opt into broadcasting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


@runtime_checkable
class Broadcastable(Protocol):
    """Protocol for events that should be broadcast to channels.

    Implement on an Event subclass to enable automatic broadcasting
    through the BroadcastEventListener.
    """

    def broadcast_on(self) -> list[Channel]:
        """Return the channels this event should be broadcast to."""
        ...

    def broadcast_as(self) -> str:
        """Return the event name for broadcast. Defaults to class name."""
        ...

    def broadcast_with(self) -> dict[str, Any]:
        """Return the data payload for broadcast."""
        ...
