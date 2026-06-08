"""CacheManager driver branches."""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from arvel.cache import CacheManager
from arvel.cache.stores.database import CacheEntry, DatabaseStore
from arvel.cache.stores.file import FileStore
from arvel.cache.stores.null import NullStore
from arvel.config import CacheConfig, CacheDriver
from arvel.database.db import DB
from pydantic import SecretStr
from sqlalchemy import Column
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def _config(driver: CacheDriver, **overrides: object) -> CacheConfig:
    values: dict[str, object] = {"connection": driver, "prefix": "test"}
    values.update(overrides)
    return CacheConfig.model_validate(values)


def test_cache_manager_builds_file_and_null_stores(tmp_path: Path) -> None:
    file_manager = CacheManager(_config(CacheDriver.FILE, file_path=str(tmp_path)))
    null_manager = CacheManager(_config(CacheDriver.NULL))

    assert isinstance(file_manager.store(), FileStore)
    assert isinstance(null_manager.store(), NullStore)


@pytest_asyncio.fixture
async def app_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[Any]]:
    """Wire DB to a temp engine with the cache table created; monkeypatch auto-reverts."""
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(DB, "_session_maker", maker, raising=False)
    monkeypatch.setattr(DB, "_engine", engine, raising=False)
    await DatabaseStore(session_maker=maker).create_table(engine)
    try:
        yield maker
    finally:
        await engine.dispose()


async def test_database_driver_uses_app_connection(
    app_db: async_sessionmaker[Any],
) -> None:
    manager = CacheManager(_config(CacheDriver.DATABASE))
    store = manager.store()
    assert isinstance(store, DatabaseStore)

    await manager.put("k", "v", ttl=60)

    # The write must land in the app's configured connection, not a throwaway
    # :memory: engine — read it straight from that connection.
    async with app_db() as session:
        entry = await session.get(CacheEntry, "test:k")
    assert entry is not None
    assert await manager.get("k") == "v"


def test_database_driver_without_db_configured_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DB, "_session_maker", None, raising=False)
    manager = CacheManager(_config(CacheDriver.DATABASE))

    with pytest.raises(RuntimeError, match="DB not configured"):
        manager.store()


class _RecordingExecutor:
    """Captures emitted DDL so the migration can be asserted without a live DB.

    Implements the `_Executor` protocol surface; only ``create_table`` records.
    """

    def __init__(self) -> None:
        self.tables: list[tuple[str, list[str]]] = []

    def create_table(self, name: str, *columns: Column[Any], **_kw: Any) -> None:
        self.tables.append((name, [c.name for c in columns]))

    def drop_table(self, name: str, **_kw: Any) -> None: ...
    def add_column(self, table_name: str, column: Column[Any], **_kw: Any) -> None: ...
    def drop_column(self, table_name: str, column_name: str, **_kw: Any) -> None: ...
    def create_index(self, name: str, table: str, columns: list[str | Any], **_kw: Any) -> None: ...
    def drop_index(self, name: str, table_name: str | None = None, **_kw: Any) -> None: ...
    def execute(self, clause: Any, **_kw: Any) -> None: ...


async def test_cache_migration_matches_database_store_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The published migration must create the exact table/columns DatabaseStore reads.
    from arvel.cache.migrations import create_cache_table
    from arvel.database import schema as schema_mod

    recorder = _RecordingExecutor()
    monkeypatch.setattr(schema_mod, "_default_executor", lambda: recorder)
    await create_cache_table.up(schema_mod.Schema())

    assert len(recorder.tables) == 1
    name, columns = recorder.tables[0]
    assert name == CacheEntry.__tablename__ == "cache_entries"
    assert set(columns) == {"key", "value", "expires_at"}


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
