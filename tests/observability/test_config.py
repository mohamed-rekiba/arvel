"""Tests for ObservabilitySettings configuration — FR-010, FR-011, NFR-005."""

from __future__ import annotations

from arvel.observability.config import ObservabilitySettings


class TestObservabilitySettings:
    def test_defaults(self, clean_env: None) -> None:
        settings = ObservabilitySettings()
        assert settings.log_level == "info"
        assert settings.log_format == "auto"
        assert settings.log_color_mode == "auto"
        assert settings.log_color_disable_in_ci is True
        assert settings.log_default_channel == "stderr"
        assert settings.log_channels["stderr"] == "stderr"
        assert settings.log_channels["single"] == "single"
        assert settings.log_channels["daily"] == "daily"
        assert settings.log_channel_levels == {}
        assert settings.log_channel_paths["single"] == ".tests/storage/logs/app.log"
        assert settings.log_channel_paths["daily"] == ".tests/storage/logs/app-daily.log"
        assert settings.log_retention_days == 14
        assert settings.otel_enabled is False
        assert settings.health_timeout == 5.0
        assert settings.sentry_dsn == ""
        assert settings.sentry_traces_sample_rate == 0.0

    def test_default_redact_patterns(self, clean_env: None) -> None:
        settings = ObservabilitySettings()
        assert "password" in settings.log_redact_patterns
        assert "token" in settings.log_redact_patterns
        assert "secret" in settings.log_redact_patterns
        assert "authorization" in settings.log_redact_patterns
        assert "api_key" in settings.log_redact_patterns
        assert "cookie" in settings.log_redact_patterns

    def test_custom_values(self) -> None:
        settings = ObservabilitySettings(
            log_level="debug",
            log_format="json",
            log_color_mode="on",
            log_color_disable_in_ci=False,
            log_default_channel="app",
            log_channels={"app": "stderr", "audit": "daily"},
            log_channel_levels={"app": "warning", "audit": "error"},
            log_channel_paths={"single": "var/log/app.log", "daily": "var/log/app-daily.log"},
            log_retention_days=7,
            otel_enabled=True,
            otel_service_name="my-app",
            otel_exporter_endpoint="http://collector:4317",
            health_timeout=10.0,
            sentry_dsn="https://key@sentry.io/123",
            sentry_traces_sample_rate=0.5,
        )
        assert settings.log_level == "debug"
        assert settings.log_format == "json"
        assert settings.log_color_mode == "on"
        assert settings.log_color_disable_in_ci is False
        assert settings.log_default_channel == "app"
        assert settings.log_channels["app"] == "stderr"
        assert settings.log_channels["audit"] == "daily"
        assert settings.log_channel_levels["app"] == "warning"
        assert settings.log_channel_levels["audit"] == "error"
        assert settings.log_channel_paths["single"] == "var/log/app.log"
        assert settings.log_channel_paths["daily"] == "var/log/app-daily.log"
        assert settings.log_retention_days == 7
        assert settings.otel_enabled is True
        assert settings.otel_service_name == "my-app"
        assert settings.otel_exporter_endpoint == "http://collector:4317"
        assert settings.health_timeout == 10.0
        assert settings.sentry_dsn == "https://key@sentry.io/123"
        assert settings.sentry_traces_sample_rate == 0.5
