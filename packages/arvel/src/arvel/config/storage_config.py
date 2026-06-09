"""Typed storage configuration (``STORAGE_*`` env vars)."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings


class LocalConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="STORAGE_LOCAL_", extra="ignore")
    __config_path__ = "filesystems.disks.local"

    root: str = "storage/app"
    url: str = ""
    # Laravel's `serve => true`: when on (and `url` is a relative path), the framework
    # registers a route that serves files from `root`. Turn off behind a CDN/object store.
    serve: bool = True


class S3Config(ArvelSettings):
    """AWS S3 or any S3-compatible provider (MinIO, R2, Hetzner, B2, …).

    Point ``endpoint`` at a non-AWS S3 endpoint to use a compatible provider.
    See ``docs/site/filesystem.md`` for per-provider worked examples.
    """

    model_config = SettingsConfigDict(env_prefix="STORAGE_S3_", extra="ignore")
    __config_path__ = "filesystems.disks.s3"

    key: SecretStr = SecretStr("")
    secret: SecretStr = SecretStr("")
    region: str = "us-east-1"
    bucket: str = ""
    endpoint: str = ""
    public_url: str = ""
    addressing_style: Literal["auto", "virtual", "path"] = "auto"
    signature_version: str = "s3v4"


class GcsConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="STORAGE_GCS_", extra="ignore")
    __config_path__ = "filesystems.disks.gcs"

    project: str = ""
    bucket: str = ""
    credentials_json: str = ""


class AzureConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="STORAGE_AZURE_", extra="ignore")
    __config_path__ = "filesystems.disks.azure"

    account: str = ""
    key: SecretStr = SecretStr("")
    container: str = ""


class StorageConfig(ArvelSettings):
    """Storage subsystem settings.

    Env vars (auto-prefixed ``STORAGE_``):

    - ``STORAGE_DEFAULT``   (default: ``local``)
    """

    model_config = SettingsConfigDict(env_prefix="STORAGE_")
    __config_path__ = "filesystems"

    default: str = "local"


__all__ = ["AzureConfig", "GcsConfig", "LocalConfig", "S3Config", "StorageConfig"]
