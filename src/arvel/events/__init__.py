"""arvel.events — the event dispatcher (custom-by-design; DR-0002).

Reached by other capabilities through the ``contracts.EventDispatcher`` resolved
from the container (e.g. the ORM dispatches model events without importing this
module). Grounded in knowledge/port/11-events.md.
"""

from __future__ import annotations

from arvel.events.dispatcher import (
    Dispatcher,
    ShouldBroadcast,
    ShouldBroadcastNow,
    ShouldDispatchAfterCommit,
    ShouldQueue,
)

__all__ = [
    "Dispatcher",
    "ShouldBroadcast",
    "ShouldBroadcastNow",
    "ShouldDispatchAfterCommit",
    "ShouldQueue",
]
