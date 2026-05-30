"""StorageManager driver coverage."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from arvel.config.storage_config import (
    AzureConfig,
    GcsConfig,
    LocalConfig,
    S3Config,
    StorageConfig,
)
from arvel.storage.drivers.local import LocalDriver
from arvel.storage.drivers.memory import MemoryDriver
from arvel.storage.manager import StorageManager
from pydantic import SecretStr


def test_storage_manager_caches_named_disks(tmp_path: Path) -> None:
    manager = StorageManager(
        StorageConfig(default="local"),
        local_config=LocalConfig(root=str(tmp_path), url="https://cdn.example.test"),
        app_key="key",
    )

    first = manager.disk()
    second = manager.disk("local")

    assert first is second
    assert isinstance(first, LocalDriver)


def test_storage_manager_creates_memory_disk() -> None:
    manager = StorageManager(StorageConfig(default="memory"))
    assert isinstance(manager.disk(), MemoryDriver)


def test_storage_manager_reports_missing_cloud_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import_module = importlib.import_module

    def import_module(name: str) -> object:
        if name in {"aioboto3", "boto3", "google.cloud.storage", "azure.storage.blob.aio"}:
            raise ImportError(name)
        return original_import_module(name)

    monkeypatch.setattr(importlib, "import_module", import_module)

    s3 = StorageManager(
        StorageConfig(default="s3"),
        s3_config=S3Config(bucket="bucket", key=SecretStr("key"), secret=SecretStr("secret")),
    )
    gcs = StorageManager(StorageConfig(default="gcs"), gcs_config=GcsConfig(bucket="bucket"))
    azure = StorageManager(
        StorageConfig(default="azure"),
        azure_config=AzureConfig(account="acct", container="container"),
    )

    with pytest.raises(ImportError, match="arvel\\[s3\\]"):
        s3.disk()
    with pytest.raises(ImportError, match="arvel\\[gcs\\]"):
        gcs.disk()
    with pytest.raises(ImportError, match="arvel\\[azure\\]"):
        azure.disk()


def test_storage_manager_rejects_unknown_driver() -> None:
    manager = StorageManager(StorageConfig(default="unknown"))

    with pytest.raises(ValueError, match="Unsupported storage driver"):
        manager.disk()
