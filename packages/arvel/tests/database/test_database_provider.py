"""DatabaseServiceProvider and DbConfig."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from arvel.application import ApplicationBuilder
from arvel.config import DbConfig
from arvel.database.schema import Schema
from arvel.providers import ConfigServiceProvider, DatabaseServiceProvider
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture
def isolated_env(clean_env: None, tmp_app_path: Path) -> Path:
    os.environ["DB_CONNECTION"] = "memory"
    return tmp_app_path


def test_db_config_defaults() -> None:
    cfg = DbConfig()
    assert cfg.connection is None
    assert cfg.url is None
    assert not cfg.enabled
    assert cfg.pool_size == 5
    assert cfg.max_overflow == 10


def test_db_config_enabled_when_connection_set(clean_env: None) -> None:
    os.environ["DB_CONNECTION"] = "postgresql"
    cfg = DbConfig()
    assert cfg.enabled


def test_db_config_enabled_when_url_set(clean_env: None) -> None:
    os.environ["DB_URL"] = "sqlite+aiosqlite:///:memory:"
    cfg = DbConfig()
    assert cfg.enabled


def test_db_config_not_enabled_when_nothing_set(clean_env: None) -> None:
    cfg = DbConfig()
    assert not cfg.enabled


def test_db_config_async_url_for_memory() -> None:
    cfg = DbConfig(connection="memory")
    assert cfg.async_url() == "sqlite+aiosqlite:///:memory:"


def test_db_config_async_url_for_sqlite_with_database() -> None:
    cfg = DbConfig(connection="sqlite", database=":memory:")
    assert cfg.async_url() == "sqlite+aiosqlite:///:memory:"


def test_db_config_async_url_for_sqlite_default_path(tmp_path: Path) -> None:
    cfg = DbConfig(connection="sqlite")
    url = cfg.async_url(base_path=tmp_path)
    assert url == f"sqlite+aiosqlite:///{tmp_path}/database/database.sqlite"


def test_db_config_async_url_for_postgres_includes_credentials() -> None:
    cfg = DbConfig(
        connection="postgresql",
        host="db",
        port=5432,
        database="app",
        username="u",
        password=SecretStr("p"),
    )
    url = cfg.async_url()
    assert "u:p@db:5432/app" in url
    assert url.startswith("postgresql+asyncpg://")


def test_db_config_driver_mapping_postgres_alias() -> None:
    cfg = DbConfig(connection="postgres", host="h", database="d")
    assert cfg.async_url().startswith("postgresql+asyncpg://")


def test_db_config_driver_mapping_mysql() -> None:
    cfg = DbConfig(connection="mysql", host="h", database="d")
    assert cfg.async_url().startswith("mysql+aiomysql://")


def test_db_config_url_wins_over_connection(clean_env: None) -> None:
    os.environ["DB_URL"] = "postgresql+asyncpg://u:p@host/app"
    os.environ["DB_CONNECTION"] = "sqlite"
    cfg = DbConfig()
    assert cfg.async_url() == "postgresql+asyncpg://u:p@host/app"


def test_db_config_public_repr_omits_password() -> None:
    cfg = DbConfig(
        connection="postgresql",
        host="db",
        port=5432,
        database="app",
        username="u",
        password=SecretStr("secret"),
    )
    repr_ = cfg.public_repr()
    assert "secret" not in repr_
    assert "db" in repr_


def test_db_config_public_repr_redacts_url_password(clean_env: None) -> None:
    os.environ["DB_URL"] = "postgresql+asyncpg://u:supersecret@host:5432/app"
    cfg = DbConfig()
    repr_ = cfg.public_repr()
    assert "supersecret" not in repr_
    assert "u:***@host:5432/app" in repr_


def test_db_config_from_dot_env_file(
    clean_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("APP_NAME=MyApp\nDB_CONNECTION=sqlite\nDB_DATABASE=:memory:\n")
    cfg = DbConfig()
    assert cfg.async_url() == "sqlite+aiosqlite:///:memory:"


async def test_database_provider_binds_engine_and_session_maker(
    isolated_env: Path,
) -> None:
    app = (
        ApplicationBuilder(base_path=isolated_env)
        .with_providers([ConfigServiceProvider, DatabaseServiceProvider])
        .create()
    )
    await app.boot()
    try:
        engine = app.container.make(AsyncEngine)
        assert isinstance(engine, AsyncEngine)

        maker = app.container.make(async_sessionmaker[AsyncSession])
        assert isinstance(maker, async_sessionmaker)

        schema_class: Any = app.container.make(Schema)
        assert schema_class is Schema
    finally:
        await app.shutdown()


async def test_database_provider_skips_ping_when_not_configured(
    clean_env: None, tmp_app_path: Path
) -> None:
    """When DB_CONNECTION and DB_URL are both absent, boot doesn't try to connect."""
    app = (
        ApplicationBuilder(base_path=tmp_app_path)
        .with_providers([DatabaseServiceProvider])
        .create()
    )
    # Should not raise even though no database is configured.
    await app.boot()
    await app.shutdown()
