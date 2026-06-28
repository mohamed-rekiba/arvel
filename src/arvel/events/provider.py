"""EventServiceProvider — binds the dispatcher (auto-discovered via entry point)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.events.dispatcher import Dispatcher
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class EventServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_dispatcher(app: Container) -> Dispatcher:
            return Dispatcher(app)

        self.app.singleton("events", make_dispatcher)

    def boot(self) -> None:
        """No-op; app/event providers register listeners."""
