"""Lock configuration — typed settings with LOCK_ env prefix."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class LockSettings(ModuleSettings):
    """Lock driver configuration.

    All values can be overridden via environment variables prefixed with ``LOCK_``.
    """

    model_config = SettingsConfigDict(env_prefix="LOCK_", extra="ignore")

    driver: str = "memory"
    default_ttl: int = 30
    redis_url: str = "redis://localhost:6379/0"


settings_class = LockSettings
