"""Domain event bus — dispatch events, register sync/queued listeners, auto-discovery."""

from arvel.events.dispatcher import EventDispatcher
from arvel.events.event import Event
from arvel.events.listener import Listener, queued

__all__ = [
    "Event",
    "EventDispatcher",
    "Listener",
    "queued",
]
