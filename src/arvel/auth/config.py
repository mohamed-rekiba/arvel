"""Authentication configuration."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


def _default_guards() -> dict[str, dict[str, str]]:
    return {
        "api": {"driver": "jwt", "provider": "users"},
        "api_key": {"driver": "api_key", "provider": "users"},
    }


def _default_providers() -> dict[str, dict[str, str]]:
    return {
        "users": {"driver": "orm", "model": "app.models.user.User"},
    }


def _default_passwords() -> dict[str, dict[str, int | str]]:
    return {
        "users": {"table": "password_resets", "expire_minutes": 60},
    }


class AuthSettings(ModuleSettings):
    """Auth module settings."""

    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")
    config_name: ClassVar[str] = "auth"

    default_guard: str = "api"
    default_passwords: str = "users"
    guards: dict[str, dict[str, str]] = Field(default_factory=_default_guards)
    providers: dict[str, dict[str, str]] = Field(default_factory=_default_providers)
    passwords: dict[str, dict[str, int | str]] = Field(default_factory=_default_passwords)


settings_class = AuthSettings
