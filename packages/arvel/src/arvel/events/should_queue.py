"""ShouldQueue marker mixin — auto-dispatch listener via Bus."""

from __future__ import annotations


class ShouldQueue:
    """Marker mixin. When a Listener also inherits ShouldQueue, EventDispatcher
    enqueues a ListenerJob via Bus instead of calling handle() inline."""


__all__ = ["ShouldQueue"]
