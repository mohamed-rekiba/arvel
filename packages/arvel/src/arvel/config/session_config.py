"""Typed session configuration (``SESSION_*`` env vars)."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings


class SessionConfig(ArvelSettings):
    """Session subsystem settings.

    Env vars (auto-prefixed ``SESSION_``):

    - ``SESSION_DRIVER``         (default: ``cookie``)
    - ``SESSION_LIFETIME``       (seconds; default: 7200)
    - ``SESSION_ENCRYPT``        (bool; default: True)
    - ``SESSION_COOKIE_NAME``    (default: ``arvel_session``)
    - ``SESSION_SECURE``         (bool; default: False — True in production)
    - ``SESSION_SAME_SITE``      (default: ``lax``)
    - ``SESSION_FILES_PATH``     (default: ``storage/framework/sessions``)
    - ``SESSION_GC_PROBABILITY`` (default: 2 — percentage)
    - ``SESSION_SECRET_KEY``     (required when encrypt=True)
    - ``SESSION_REDIS_URL``      (default: ``redis://127.0.0.1:6379/0``)
    - ``SESSION_REDIS_PREFIX``   (default: ``arvel:``)
    - ``SESSION_DATABASE_URL``   (default: ``sqlite+aiosqlite:///sessions.db``)
    """

    model_config = SettingsConfigDict(env_prefix="SESSION_")

    driver: str = "cookie"
    lifetime: int = 7200
    encrypt: bool = True
    cookie_name: str = "arvel_session"
    secure: bool = False
    same_site: str = "lax"
    files_path: str = "storage/framework/sessions"
    gc_probability: int = 2
    secret_key: SecretStr = SecretStr("")
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_prefix: str = "arvel:"
    database_url: str = "sqlite+aiosqlite:///sessions.db"


__all__ = ["SessionConfig"]
