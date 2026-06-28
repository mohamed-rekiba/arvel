"""The framework's own root service provider (entry-point target).

Registered via ``[project.entry-points."arvel.providers"]`` in pyproject so it is
auto-discovered exactly like an ecosystem package's provider. A near-empty
provider at this stage; core service bindings are added as the kernel grows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.kernel.exceptions import ExceptionHandler
from arvel.kernel.logging import LogManager
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.kernel.container import Container


class KernelServiceProvider(ServiceProvider):
    """Binds the framework's core services into the container."""

    def register(self) -> None:
        def make_log(_app: Container) -> LogManager:
            return LogManager()

        def make_exceptions(app: Container) -> ExceptionHandler:
            return ExceptionHandler(app.make("log"))

        self.app.singleton("log", make_log)
        self.app.singleton("exceptions", make_exceptions)

    def boot(self) -> None:
        """Boot-time wiring. (No-op until later kernel services.)"""

    def provides(self) -> list[Any]:
        return []
