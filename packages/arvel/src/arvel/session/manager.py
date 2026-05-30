"""SessionManager — driver factory for session stores."""

from __future__ import annotations

import importlib
from typing import Any

from arvel.config.session_config import SessionConfig
from arvel.session.data import SessionData
from arvel.session.store import SessionStore


class SessionManager:
    """Creates and caches session store instances keyed by driver name."""

    def __init__(self, config: SessionConfig) -> None:
        self._config = config
        self._stores: dict[str, SessionStore] = {}

    def store(self, name: str | None = None) -> SessionStore:
        driver = name or self._config.driver
        if driver not in self._stores:
            self._stores[driver] = self._create(driver)
        return self._stores[driver]

    def _create(self, driver: str) -> SessionStore:
        match driver:
            case "cookie":
                from arvel.session.stores.cookie import CookieStore

                return CookieStore(
                    app_key=self._config.secret_key.get_secret_value().encode(),
                    lifetime=self._config.lifetime,
                    cookie_name=self._config.cookie_name,
                )
            case "redis":
                from typing import Any as _Any

                from arvel.session.stores.redis import RedisSessionStore

                try:
                    _aioredis = importlib.import_module("redis.asyncio")
                except ImportError as exc:
                    raise ImportError(
                        "SessionManager redis driver requires arvel[redis]. "
                        "Install with: pip install 'arvel[redis]'"
                    ) from exc

                client: _Any = _aioredis.from_url(self._config.redis_url)
                return RedisSessionStore(
                    redis=client,
                    prefix=f"{self._config.redis_prefix}session:",
                    lifetime=self._config.lifetime,
                )
            case "database":
                from sqlalchemy.ext.asyncio import (
                    async_sessionmaker,
                    create_async_engine,
                )

                from arvel.session.stores.database import DatabaseSessionStore

                engine = create_async_engine(self._config.database_url)
                maker = async_sessionmaker(engine, expire_on_commit=False)
                return DatabaseSessionStore(session_maker=maker)
            case "file":
                from arvel.session.stores.file import FileSessionStore

                return FileSessionStore(self._config.files_path)
            case _:
                raise ValueError(f"Unsupported session driver: {driver!r}")

    async def create_session(self, session_id: str | None = None) -> SessionData:
        """Load session data from the default store and wrap in SessionData."""
        store = self.store()
        if session_id:
            raw: dict[str, Any] = await store.read(session_id)
        else:
            raw = {}
        data = SessionData(raw)
        data.finalize_flash()
        return data

    async def save_session(self, session: SessionData) -> None:
        """Persist session data back to the store."""
        store = self.store()
        await store.write(session.get_id(), session.to_dict(), self._config.lifetime)


__all__ = ["SessionManager"]
