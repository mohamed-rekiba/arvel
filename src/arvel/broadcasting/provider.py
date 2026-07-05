"""BroadcastServiceProvider — binds the Broadcast manager.

Not yet wired into ``[project.entry-points."arvel.providers"]`` (that one-line pyproject edit is
outside this change's scope — see the story-19 handoff notes); an app that wants auto-discovery
needs it added there. Until then, bind manually: ``app.instance("broadcast",
BroadcastManager(app))``, or call this provider's ``register()`` yourself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.broadcasting import BroadcastManager
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class BroadcastServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_broadcast(app: Container) -> BroadcastManager:
            return BroadcastManager(app)

        self.app.singleton("broadcast", make_broadcast)

    def boot(self) -> None:
        """No-op."""
