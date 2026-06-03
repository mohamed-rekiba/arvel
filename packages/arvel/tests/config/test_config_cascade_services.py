"""Per-service cascade: config/*.py drives the typed settings classes.

Locks the wiring for storage, database, and cache so the contract can't
silently regress.
"""

from __future__ import annotations

import os
import types
from collections.abc import Iterator

import pytest
from arvel.config import _lookup_registry as reg


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    env_snapshot = dict(os.environ)
    reg.reset()
    try:
        yield
    finally:
        reg.reset()
        os.environ.clear()
        os.environ.update(env_snapshot)


def test_storage_default_and_s3_resolve_from_filesystems() -> None:
    from arvel.config.storage_config import S3Config, StorageConfig

    reg.register(
        "filesystems",
        types.SimpleNamespace(
            default="s3",
            disks={
                "local": {"root": "var/app", "url": "/media"},
                "s3": {"bucket": "kit-bucket", "region": "eu-west-1", "key": "ak", "secret": "sk"},
            },
        ),
    )

    assert StorageConfig().default == "s3"
    s3 = S3Config()
    assert s3.bucket == "kit-bucket"
    assert s3.region == "eu-west-1"
    assert s3.secret.get_secret_value() == "sk"


def test_storage_env_fallback_when_no_config() -> None:
    from arvel.config.storage_config import StorageConfig

    os.environ["STORAGE_DEFAULT"] = "s3"
    assert StorageConfig().default == "s3"


def test_database_resolves_selected_named_connection() -> None:
    from arvel.config.db_config import DbConfig

    reg.register(
        "database",
        types.SimpleNamespace(
            default="postgresql",
            connections={
                "sqlite": {"url": "sqlite+aiosqlite:///:memory:"},
                "postgresql": {
                    "host": "db.internal",
                    "port": 5432,
                    "database": "shop",
                    "username": "app",
                },
            },
        ),
    )

    cfg = DbConfig()
    assert cfg.connection == "postgresql"
    assert cfg.host == "db.internal"
    assert cfg.port == 5432
    assert cfg.database == "shop"


def test_cache_store_resolves_and_injects_connection() -> None:
    from arvel.config.cache_config import CacheConfig, CacheDriver

    reg.register(
        "cache",
        types.SimpleNamespace(
            default="redis",
            stores={"redis": {"url": "redis://cache:6379/1", "prefix": "shop:"}},
        ),
    )

    cfg = CacheConfig()
    assert cfg.connection == CacheDriver.REDIS
    assert cfg.url == "redis://cache:6379/1"
    assert cfg.prefix == "shop:"


def test_config_file_wins_over_env_for_storage() -> None:
    from arvel.config.storage_config import StorageConfig

    os.environ["STORAGE_DEFAULT"] = "local"
    reg.register("filesystems", types.SimpleNamespace(default="s3", disks={}))
    assert StorageConfig().default == "s3"
