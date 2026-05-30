"""ListenerRegistry — allowlist for ShouldQueue listener deserialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.events.listener import Listener

# Maps "module.ClassName" -> Listener subclass.
# Populated by Listener.__init_subclass__ for ShouldQueue listeners.
ListenerRegistry: dict[str, type[Listener[Any]]] = {}


__all__ = ["ListenerRegistry"]
