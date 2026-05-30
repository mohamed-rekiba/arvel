"""NotificationConfig coverage."""

from __future__ import annotations

from arvel.notifications.config import NotificationConfig


def test_notification_config_defaults_and_env_prefix() -> None:
    config = NotificationConfig()

    assert config.default_channel == "mail"
    assert config.model_config.get("env_prefix") == "NOTIFICATION_"
