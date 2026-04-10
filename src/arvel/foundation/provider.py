"""Service provider base class — lifecycle hooks for module registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class ServiceProvider:
    """Base for all module service providers.

    Lower ``priority`` boots first. Framework: 0-20, user: 50 (default).
    """

    priority: int = 50

    def configure(self, config: AppSettings) -> None:
        """Capture loaded config so factories use .env values, not bare defaults."""

    async def register(self, container: ContainerBuilder) -> None:
        """Declare DI bindings. Don't resolve here — container isn't built yet."""

    async def boot(self, app: Application) -> None:
        """Late-stage wiring: routes, listeners, middleware, resolved deps."""

    async def shutdown(self, app: Application) -> None:
        """Release long-lived resources. Called in reverse provider order."""
