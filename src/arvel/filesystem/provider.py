"""FilesystemServiceProvider — binds the Storage manager (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.filesystem import FilesystemManager
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class FilesystemServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_filesystem(app: Container) -> FilesystemManager:
            return FilesystemManager(app)

        self.app.singleton("filesystem", make_filesystem)

    def boot(self) -> None:
        """No-op."""
