"""RoutingServiceProvider — binds the Router (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.routing import Router

if TYPE_CHECKING:
    from arvel.contracts import Container


class RoutingServiceProvider(ServiceProvider):
    def register(self) -> None:
        if self.app.bound("router"):
            return  # respect a router the app already provided (don't clobber an override)

        def make_router(_app: Container) -> Router:
            return Router()

        self.app.singleton("router", make_router)

    def boot(self) -> None:
        """No-op."""
