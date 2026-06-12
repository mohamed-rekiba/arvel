"""SessionManager — driver factory for session stores."""

from __future__ import annotations

import importlib
from typing import Any

from arvel.config.session_config import SessionConfig, SessionDriver
from arvel.session.cipher import SessionCipher
from arvel.session.data import SessionData
from arvel.session.store import SessionStore


class SessionManager:
    """Creates and caches session store instances keyed by driver name."""

    def __init__(self, config: SessionConfig) -> None:
        self._config = config
        self._stores: dict[SessionDriver, SessionStore] = {}

    def store(self, name: SessionDriver | str | None = None) -> SessionStore:
        driver = self._config.driver if name is None else SessionDriver(name)
        if driver not in self._stores:
            self._stores[driver] = self._create(driver)
        return self._stores[driver]

    def _payload_cipher(self) -> SessionCipher | None:
        """Cipher for at-rest server-side payloads, or None when encryption is off.

        Honors ``SESSION_ENCRYPT`` for file/database/redis the same way the cookie
        driver always encrypts — so the flag means the same thing everywhere.
        """
        if not self._config.encrypt:
            return None
        secret = self._config.secret_key.get_secret_value()
        if not secret:
            raise ValueError(
                "SESSION_SECRET_KEY is required when SESSION_ENCRYPT is true — "
                "it derives the keys that encrypt the session payload at rest. "
                "Set SESSION_SECRET_KEY (or set SESSION_ENCRYPT=false)."
            )
        return SessionCipher.from_app_key(secret.encode())

    def _create(self, driver: SessionDriver) -> SessionStore:
        match driver:
            case SessionDriver.ARRAY:
                # Test-only. Loses all sessions on process exit; never use in
                # production. Registered so config('session.driver', 'array')
                # produces a real in-memory store instead of raising.
                from arvel.session.stores.array import ArraySessionStore

                return ArraySessionStore(lifetime=self._config.lifetime)
            case SessionDriver.COOKIE:
                from arvel.session.stores.cookie import CookieStore

                secret = self._config.secret_key.get_secret_value()
                if not secret:
                    raise ValueError(
                        "SESSION_SECRET_KEY is required for the cookie session driver — "
                        "it derives the AES/HMAC keys that encrypt the cookie payload. "
                        "Set SESSION_SECRET_KEY (or switch SESSION_DRIVER to file/redis/database)."
                    )
                return CookieStore(
                    app_key=secret.encode(),
                    lifetime=self._config.lifetime,
                    cookie_name=self._config.cookie_name,
                )
            case SessionDriver.REDIS:
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
                    cipher=self._payload_cipher(),
                )
            case SessionDriver.DATABASE:
                from sqlalchemy.ext.asyncio import (
                    async_sessionmaker,
                    create_async_engine,
                )

                from arvel.session.stores.database import DatabaseSessionStore

                engine = create_async_engine(self._config.database_url)
                maker = async_sessionmaker(engine, expire_on_commit=False)
                return DatabaseSessionStore(
                    session_maker=maker,
                    lifetime=self._config.lifetime,
                    cipher=self._payload_cipher(),
                )
            case SessionDriver.FILE:
                from arvel.session.stores.file import FileSessionStore

                return FileSessionStore(
                    self._config.files_path,
                    lifetime=self._config.lifetime,
                    cipher=self._payload_cipher(),
                )

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
        await store.write(session.get_id(), session.to_dict())
        # Drop ids rotated out by regenerate() so the old record can't outlive the
        # new one — mirrors StartSession._persist for the facade-driven path.
        for old_id in session.drain_pending_destroy():
            await store.destroy(old_id)


__all__ = ["SessionManager"]
