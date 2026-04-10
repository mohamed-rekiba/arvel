"""Shared fixtures for observability tests."""

from __future__ import annotations

import os

import pytest

from arvel.observability.config import ObservabilitySettings

_TEMP_LOG_CHANNEL_PATHS = """{
        "single": ".tests/storage/logs/app.log",
        "daily": ".tests/storage/logs/app-daily.log"
    }"""


@pytest.fixture(autouse=True)
def _route_logs_to_temp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect file-based log channels into ``.tests/`` for every observability test."""
    monkeypatch.setenv("OBSERVABILITY_LOG_CHANNEL_PATHS", _TEMP_LOG_CHANNEL_PATHS)
    for key in list(os.environ):
        if key.startswith("OBSERVABILITY_") and key != "OBSERVABILITY_LOG_CHANNEL_PATHS":
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def obs_settings() -> ObservabilitySettings:
    return ObservabilitySettings(
        log_level="debug",
        log_format="console",
        log_redact_patterns=("password", "token", "secret", "authorization", "api_key", "cookie"),
        otel_enabled=False,
        health_timeout=2.0,
        sentry_dsn="",
    )


@pytest.fixture
def obs_settings_production() -> ObservabilitySettings:
    return ObservabilitySettings(
        log_level="info",
        log_format="json",
        otel_enabled=False,
        health_timeout=5.0,
        sentry_dsn="",
    )
