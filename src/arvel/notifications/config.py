"""Notification configuration — typed settings with NOTIFICATION_ env prefix."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class NotificationSettings(ModuleSettings):
    """Notification configuration.

    All values can be overridden via environment variables prefixed with ``NOTIFICATION_``.
    """

    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_", extra="ignore")
    config_name: ClassVar[str] = "notifications"

    default_channels: list[str] = Field(default_factory=lambda: ["mail"])
    slack_webhook_url: SecretStr = SecretStr("")
    database_table: str = "notifications"


settings_class = NotificationSettings
