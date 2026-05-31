"""Database service provider — engine, session-maker, request-scoped session, Schema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from arvel.config import DbConfig
from arvel.database.db import DB
from arvel.database.exceptions import DatabaseConnectionError
from arvel.database.schema import Schema
from arvel.providers.service_provider import ServiceProvider

_PING = text("SELECT 1")


@dataclass(frozen=True, slots=True)
class _RegistryConn:
    url: str
    echo: bool
    pool_size: int
    max_overflow: int
    pool_recycle: int


class DatabaseServiceProvider(ServiceProvider):
    """Bind the async engine, session-maker, and a per-request session factory.

    Bindings:

    - :class:`DbConfig` — bound only if not already registered.
    - :class:`~sqlalchemy.ext.asyncio.AsyncEngine` — singleton, built lazily.
    - :class:`~sqlalchemy.ext.asyncio.async_sessionmaker` — singleton.
    - :class:`~sqlalchemy.ext.asyncio.AsyncSession` — scoped (fresh per resolution).
    - :class:`~arvel.database.schema.Schema` — singleton facade.

    When neither ``DB_URL`` nor ``DB_CONNECTION`` is configured **and** no
    ``config/database.py`` is present, ``enabled`` is ``False`` and ``boot()``
    skips the connection ping. This lets pure API-gateway apps run without a
    database.
    """

    def register(self) -> None:
        c = self.app.container

        c.instance(Schema, cast("Schema", Schema))
        c.singleton(AsyncEngine, self._engine_factory)
        c.singleton(async_sessionmaker, self._session_maker_factory)
        c.bind(AsyncSession, self._session_factory)

    async def boot(self) -> None:
        registry_conn = self._connection_from_registry()
        cfg = self._config()

        # Skip the ping when the database is not configured at all.
        if registry_conn is None and not cfg.enabled:
            return

        engine = self.app.container.make(AsyncEngine)
        try:
            async with engine.connect() as conn:
                await conn.execute(_PING)
        except SQLAlchemyError as exc:
            if registry_conn is not None:
                raw_url = registry_conn.url
                driver = raw_url.split("://")[0] if "://" in raw_url else "sqlite"
                host = raw_url.split("@")[-1].split("/")[0] if "@" in raw_url else "<local>"
            else:
                url = cfg.async_url(self._base_path())
                driver = url.split("://")[0] if "://" in url else "sqlite"
                host = url.split("@")[-1].split("/")[0] if "@" in url else "<local>"
            raise DatabaseConnectionError(driver=driver, host=host, inner=exc) from exc

        maker: async_sessionmaker[AsyncSession] = self.app.container.make(
            async_sessionmaker[AsyncSession]
        )
        DB.configure(maker)
        DB.configure_engine(engine)
        from arvel.database.events import configure_observer_container

        configure_observer_container(self.app.container)

        from arvel.database.service import DatabaseService

        self.app.register_service(DatabaseService(self.app.container))

    async def shutdown(self) -> None:
        try:
            engine = self.app.container.make(AsyncEngine)
        except Exception:  # pragma: no cover
            return
        await engine.dispose()

    # ------------------------------------------------------------------ helpers

    def _config(self) -> DbConfig:
        return self.safe_config(DbConfig, default=DbConfig())

    def _base_path(self) -> Path | None:
        from arvel.application.errors import EnvironmentNotSetError

        try:
            return self.app.base_path()
        except EnvironmentNotSetError, AttributeError:
            return None

    def _engine_factory(self) -> AsyncEngine:
        registry_conn = self._connection_from_registry()
        if registry_conn is not None:
            url = registry_conn.url
            echo = registry_conn.echo
            pool_size = registry_conn.pool_size
            max_overflow = registry_conn.max_overflow
            pool_recycle = registry_conn.pool_recycle
        else:
            cfg = self._config()
            url = cfg.async_url(self._base_path())
            echo = cfg.echo
            pool_size = cfg.pool_size
            max_overflow = cfg.max_overflow
            pool_recycle = cfg.pool_recycle

        kwargs: dict[str, object] = {"echo": echo}
        driver = url.split("://")[0] if "://" in url else "sqlite"
        if not driver.startswith("sqlite"):
            kwargs["pool_size"] = pool_size
            kwargs["max_overflow"] = max_overflow
            kwargs["pool_recycle"] = pool_recycle
        return create_async_engine(url, **kwargs)

    def _connection_from_registry(self) -> _RegistryConn | None:
        """Read connection params from ``config/database.py`` via the dotted-key registry.

        Returns ``None`` to fall back to ``DbConfig`` env vars when the file
        is absent or the default connection dict is missing.
        """
        from arvel.config._lookup_registry import config as _cfg

        default = _cfg("database.default")
        if default is None:
            return None
        conn = _cfg(f"database.connections.{default}")
        if not isinstance(conn, dict):
            return None
        raw: dict[str, Any] = cast("dict[str, Any]", conn)
        url = str(raw.get("url", "sqlite+aiosqlite:///:memory:"))
        echo = bool(raw.get("echo", False))
        pool_size = int(raw.get("pool_size", 5))
        max_overflow = int(raw.get("max_overflow", 10))
        pool_recycle = int(raw.get("pool_recycle", 1800))
        return _RegistryConn(
            url=url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
        )

    def _session_maker_factory(self) -> async_sessionmaker[AsyncSession]:
        engine = self.app.container.make(AsyncEngine)
        return async_sessionmaker(engine, expire_on_commit=False)

    def _session_factory(self) -> AsyncSession:
        maker = self.app.container.make(async_sessionmaker[AsyncSession])
        return maker()


__all__ = ["DatabaseServiceProvider"]
