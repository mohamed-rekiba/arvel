"""Notification configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class NotificationConfig(BaseSettings):
    """Top-level notifications settings."""

    default_channel: str = "mail"

    model_config = {"env_prefix": "NOTIFICATION_"}


__all__ = ["NotificationConfig"]
