"""Service provider base class — two-phase lifecycle for module registration.

Each module's provider.py exports a subclass of ServiceProvider. The kernel
calls register() on all providers first, then boot() in priority order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class ServiceProvider:
    """Base class for all module service providers.

    Attributes:
        priority: Boot order weight. Lower values boot first. Framework
            providers use 0-20; user providers default to 50.
    """

    priority: int = 50

    async def register(self, container: ContainerBuilder) -> None:
        """Declare DI bindings. Called before any boot() method.

        Override to bind interfaces to concrete implementations. Do NOT
        resolve dependencies here — the container isn't built yet.
        """

    async def boot(self, app: Application) -> None:
        """Perform late-stage wiring after all bindings are registered.

        Override to wire routes, register event listeners, configure
        middleware, or perform any setup that requires resolved dependencies.
        """

    async def shutdown(self, app: Application) -> None:
        """Release resources owned by this provider.

        Called during ``Application.shutdown()`` in reverse provider order.
        Override when a provider owns long-lived resources (worker clients,
        broker connections, background tasks, etc).
        """
