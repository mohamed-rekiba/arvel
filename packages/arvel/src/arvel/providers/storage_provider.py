"""StorageServiceProvider — registers the StorageManager and Storage facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.console import Command

_T = TypeVar("_T")


class StorageServiceProvider(ServiceProvider):
    """Binds StorageManager to the container and wires the Storage facade."""

    def register(self) -> None:
        from arvel.config.storage_config import (
            AzureConfig,
            GcsConfig,
            LocalConfig,
            S3Config,
            StorageConfig,
        )
        from arvel.facades.storage import Storage
        from arvel.storage import StorageManager

        c = self.app.container

        def _cfg(cls: type[_T], default: _T) -> _T:
            return c.make(cls) if c.bound(cls) else default

        config = _cfg(StorageConfig, StorageConfig())
        local_config = _cfg(LocalConfig, LocalConfig())
        s3_config = _cfg(S3Config, S3Config())
        gcs_config = _cfg(GcsConfig, GcsConfig())
        azure_config = _cfg(AzureConfig, AzureConfig())

        c.instance(StorageConfig, config)

        manager = StorageManager(
            config=config,
            local_config=local_config,
            s3_config=s3_config,
            gcs_config=gcs_config,
            azure_config=azure_config,
        )
        c.instance(StorageManager, manager)
        Storage.bind(c)

    async def boot(self) -> None:
        pass

    def commands(self) -> list[type[Command] | Command]:
        from arvel.console.commands.storage_link import StorageLinkCommand

        return [StorageLinkCommand]


__all__ = ["StorageServiceProvider"]
