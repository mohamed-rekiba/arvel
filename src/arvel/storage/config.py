"""Storage configuration — typed settings with STORAGE_ env prefix."""

from __future__ import annotations

from typing import ClassVar

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class StorageSettings(ModuleSettings):
    """Storage driver configuration.

    All values can be overridden via environment variables prefixed with ``STORAGE_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        extra="ignore",
    )
    config_name: ClassVar[str] = "storage"

    driver: str = "local"
    local_root: str = "storage/app"
    local_base_url: str = "/storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: SecretStr = SecretStr("")


settings_class = StorageSettings
