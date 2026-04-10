"""Observability configuration — logging, tracing, health, Sentry settings."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings

type LogDriverName = Literal["stderr", "single", "daily"]


def _default_log_channels() -> dict[str, LogDriverName]:
    return {
        "stderr": "stderr",
        "single": "single",
        "daily": "daily",
    }


def _default_log_channel_paths() -> dict[str, str]:
    return {
        "single": "storage/logs/app.log",
        "daily": "storage/logs/app-daily.log",
    }


def _empty_log_channel_levels() -> dict[str, str]:
    return {}


class ObservabilitySettings(ModuleSettings):
    """Configuration slice for the observability stack.

    Environment variables are prefixed with ``OBSERVABILITY_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="OBSERVABILITY_",
        extra="ignore",
    )

    log_level: str = "info"
    log_format: str = "auto"
    log_color_mode: Literal["auto", "on", "off"] = "auto"
    log_color_disable_in_ci: bool = True
    log_default_channel: str = "stderr"
    log_channels: dict[str, LogDriverName] = _default_log_channels()
    log_channel_levels: dict[str, str] = _empty_log_channel_levels()
    log_channel_paths: dict[str, str] = _default_log_channel_paths()
    log_retention_days: int = 14
    log_redact_patterns: tuple[str, ...] = (
        "password",
        "token",
        "secret",
        "authorization",
        "api_key",
        "cookie",
    )

    otel_enabled: bool = False
    otel_service_name: str = ""
    otel_exporter_endpoint: str = ""

    access_log_enabled: bool = True

    health_timeout: float = 5.0

    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0


settings_class = ObservabilitySettings
