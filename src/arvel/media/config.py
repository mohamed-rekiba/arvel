"""Media configuration — typed settings with MEDIA_ env prefix."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class MediaSettings(ModuleSettings):
    """Media library configuration.

    All values can be overridden via environment variables prefixed with ``MEDIA_``.
    """

    model_config = SettingsConfigDict(env_prefix="MEDIA_", extra="ignore")

    max_dimension: int = 10000
    path_prefix: str = "media"
    conversion_quality: int = 85
    conversion_format: str = "source"


settings_class = MediaSettings
