"""Typed session configuration (``SESSION_*`` env vars)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import SecretStr, field_validator
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings


class SessionDriver(StrEnum):
    ARRAY = "array"
    COOKIE = "cookie"
    REDIS = "redis"
    DATABASE = "database"
    FILE = "file"


class SameSite(StrEnum):
    """Cookie ``SameSite`` policy. Values are the lowercase config form."""

    LAX = "lax"
    STRICT = "strict"
    NONE = "none"

    @property
    def cookie_attr(self) -> str:
        """The canonical Set-Cookie attribute casing (``Lax``/``Strict``/``None``)."""
        return self.value.capitalize()

    @classmethod
    def coerce(cls, value: SameSite | str) -> SameSite:
        """Parse a config string case-insensitively; unknown values fall back to Lax."""
        if isinstance(value, cls):
            return value
        try:
            return cls(value.strip().lower())
        except ValueError:
            return cls.LAX


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
    __config_path__ = "session"

    driver: SessionDriver = SessionDriver.COOKIE
    lifetime: int = 7200
    encrypt: bool = True
    cookie_name: str = "arvel_session"
    secure: bool = False
    same_site: SameSite = SameSite.LAX
    files_path: str = "storage/framework/sessions"
    gc_probability: int = 2
    secret_key: SecretStr = SecretStr("")
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_prefix: str = "arvel:"
    database_url: str = "sqlite+aiosqlite:///sessions.db"

    @field_validator("driver", mode="before")
    @classmethod
    def _lower_driver(cls, value: object) -> object:
        # Accept SESSION_DRIVER=Cookie / COOKIE; enum values are lowercase.
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("same_site", mode="before")
    @classmethod
    def _coerce_same_site(cls, value: object) -> SameSite:
        return SameSite.coerce(value) if isinstance(value, (str, SameSite)) else SameSite.LAX


__all__ = ["SameSite", "SessionConfig", "SessionDriver"]
