"""Cache configuration — typed settings with CACHE_ env prefix."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class CacheSettings(ModuleSettings):
    """Cache driver configuration.

    All values can be overridden via environment variables prefixed with ``CACHE_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        extra="ignore",
    )

    driver: str = "memory"
    prefix: str = ""
    default_ttl: int = 3600
    redis_url: str = "redis://localhost:6379/0"


settings_class = CacheSettings
