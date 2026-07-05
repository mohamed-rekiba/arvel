"""BroadcastServiceProvider — binds the Broadcast manager.

Auto-discovered via ``[project.entry-points."arvel.providers"]``, so a fresh app resolves
``broadcast`` without manual wiring.
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
