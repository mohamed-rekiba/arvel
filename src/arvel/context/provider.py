"""ContextProvider — boots context middleware and structlog integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.foundation.provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class ContextProvider(ServiceProvider):
    """Framework-level provider for the context store.

    Priority 6 — boots after Observability (5) so logging is configured,
    but before HTTP (10) so context middleware is available.
    """

    priority: int = 6

    async def register(self, container: ContainerBuilder) -> None:
        pass

    async def boot(self, app: Application) -> None:
        pass
