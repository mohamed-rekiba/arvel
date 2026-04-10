"""MediaProvider — wires MediaContract to the default media manager."""

from __future__ import annotations

from typing import TYPE_CHECKING

import arvel.media.migration as _migration  # noqa: F401 — registers framework migration
from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider
from arvel.media.contracts import MediaContract
from arvel.media.manager import MediaManager

if TYPE_CHECKING:
    from arvel.foundation.container import ContainerBuilder


class MediaProvider(ServiceProvider):
    """Registers MediaContract with a storage-backed default manager.

    Importing this module also registers the ``create_media_table``
    framework migration via :func:`register_framework_migration`, so
    ``arvel db migrate`` auto-publishes it into the project's migrations
    directory.
    """

    priority = 12

    async def register(self, container: ContainerBuilder) -> None:
        container.provide(MediaContract, MediaManager, scope=Scope.APP)
