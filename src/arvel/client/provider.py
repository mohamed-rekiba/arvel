"""ClientServiceProvider — binds the Http client (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.client import Client
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class ClientServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_http(_app: Container) -> Client:
            return Client()

        self.app.singleton("http", make_http)

    def boot(self) -> None:
        """No-op."""
