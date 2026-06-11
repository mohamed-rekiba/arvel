"""StorageManager — driver factory for storage disks."""

from __future__ import annotations

from arvel.config.storage_config import AzureConfig, GcsConfig, LocalConfig, S3Config, StorageConfig
from arvel.storage.disk import StorageDisk


class StorageManager:
    """Creates and caches storage disk instances keyed by driver name."""

    def __init__(
        self,
        config: StorageConfig,
        local_config: LocalConfig | None = None,
        s3_config: S3Config | None = None,
        gcs_config: GcsConfig | None = None,
        azure_config: AzureConfig | None = None,
        app_key: str = "",
    ) -> None:
        self._config = config
        self._local_config = local_config or LocalConfig()
        self._s3_config = s3_config or S3Config()
        self._gcs_config = gcs_config or GcsConfig()
        self._azure_config = azure_config or AzureConfig()
        self._app_key = app_key
        self._disks: dict[str, StorageDisk] = {}

    def disk(self, name: str | None = None) -> StorageDisk:
        driver = name or self._config.default
        if driver not in self._disks:
            self._disks[driver] = self._create(driver)
        return self._disks[driver]

    def _create(self, driver: str) -> StorageDisk:
        match driver:
            case "local":
                from arvel.storage.drivers.local import LocalDriver

                return LocalDriver(
                    root=self._local_config.root,
                    base_url=self._local_config.url or "http://localhost/storage",
                    app_key=self._app_key.encode() if self._app_key else b"",
                )
            case "memory":
                from arvel.storage.drivers.memory import MemoryDriver

                return MemoryDriver()
            case "s3":
                from arvel.storage.drivers.s3 import S3Driver

                return S3Driver(config=self._s3_config)
            case "gcs":
                from arvel.storage.drivers.gcs import GcsDriver

                return GcsDriver(bucket=self._gcs_config.bucket)
            case "azure":
                from arvel.storage.drivers.azure import AzureDriver

                account_url = f"https://{self._azure_config.account}.blob.core.windows.net"
                return AzureDriver(
                    container=self._azure_config.container,
                    account_url=account_url,
                    account=self._azure_config.account,
                    account_key=self._azure_config.key.get_secret_value(),
                )
            case _:
                raise ValueError(f"Unsupported storage driver: {driver!r}")


__all__ = ["StorageManager"]
