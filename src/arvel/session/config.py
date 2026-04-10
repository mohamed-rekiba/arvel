"""Session configuration."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class SessionSettings(ModuleSettings):
    """Session module settings."""

    model_config = SettingsConfigDict(env_prefix="SESSION_", extra="ignore")
    config_name: ClassVar[str] = "session"

    driver: str = "memory"
    lifetime: int = 120
    cookie: str = "arvel_session"
    secure: bool = False
    http_only: bool = True
    same_site: Literal["lax", "strict", "none"] = "lax"


settings_class = SessionSettings
