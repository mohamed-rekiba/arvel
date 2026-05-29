"""CacheManager driver branches."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import cast

import pytest
from arvel.cache import CacheManager
from arvel.cache.stores.database import DatabaseStore
from arvel.cache.stores.file import FileStore
from arvel.cache.stores.null import NullStore
from arvel.config import CacheConfig, CacheDriver
from pydantic import SecretStr


def _config(driver: CacheDriver, **overrides: object) -> CacheConfig:
    values: dict[str, object] = {"connection": driver, "prefix": "test"}
    values.update(overrides)
    return CacheConfig.model_validate(values)


def test_cache_manager_builds_file_null_and_database_stores(tmp_path: Path) -> None:
    file_manager = CacheManager(_config(CacheDriver.FILE, file_path=str(tmp_path)))
    null_manager = CacheManager(_config(CacheDriver.NULL))
    database_manager = CacheManager(_config(CacheDriver.DATABASE))

    assert isinstance(file_manager.store(), FileStore)
    assert isinstance(null_manager.store(), NullStore)
    assert isinstance(database_manager.store(), DatabaseStore)


def test_cache_manager_redis_driver_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import_module = importlib.import_module

    def import_module(name: str) -> object:
        if name == "redis.asyncio":
            raise ImportError("missing redis")
        return real_import_module(name)

    monkeypatch.setattr(importlib, "import_module", import_module)
    manager = CacheManager(_config(CacheDriver.REDIS))

    with pytest.raises(ImportError, match=r"arvel\[redis\]"):
        manager.store()


def test_cache_manager_redis_driver_uses_url_or_host(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    class RedisModule:
        @staticmethod
        def from_url(url: str, *, decode_responses: bool) -> object:
            calls.append(("url", (url, decode_responses)))
            return object()

        @staticmethod
        def Redis(**kwargs: object) -> object:
            calls.append(("host", kwargs))
            return object()

    def import_module(name: str) -> object:
        assert name == "redis.asyncio"
        return RedisModule

    monkeypatch.setattr(importlib, "import_module", import_module)

    CacheManager(_config(CacheDriver.REDIS, url="redis://cache/0")).store()
    CacheManager(
        _config(
            CacheDriver.REDIS,
            host="cache",
            port=6380,
            database=2,
            password=SecretStr("secret"),
        )
    ).store()

    assert calls[0] == ("url", ("redis://cache/0", False))
    kind, kwargs = calls[1]
    assert kind == "host"
    assert isinstance(kwargs, dict)
    mapping = cast("dict[str, object]", kwargs)
    assert mapping["host"] == "cache"
    assert mapping["port"] == 6380
    assert mapping["db"] == 2
    assert isinstance(mapping["password"], SecretStr)
    assert mapping["password"].get_secret_value() == "secret"
