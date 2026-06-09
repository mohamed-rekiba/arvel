"""Env-var configuration wiring."""

from __future__ import annotations

import pytest


class TestObservabilityConfigEnvVars:
    def test_all_expected_fields_present(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        # Verify every documented env var maps to a config field
        expected_fields = [
            "sdk_disabled",
            "otlp_endpoint",
            "otlp_headers",
            "service_name",
            "log_level",
            "log_format",
            "log_redact_fields",
            "log_uvicorn_access",
            "metrics_enabled",
            "metrics_allowed_cidrs",
            "request_middleware_enabled",
            "db_slow_query_ms",
            "db_query_log_enabled",
        ]
        for field in expected_fields:
            assert hasattr(config, field), f"ObservabilityConfig missing field: {field}"

    def test_sdk_disabled_reads_otel_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.sdk_disabled is True

    def test_log_format_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_FORMAT", "console")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.log_format == "console"

    def test_metrics_enabled_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OBSERVABILITY_METRICS_ENABLED", "true")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.metrics_enabled is True

    def test_db_slow_query_ms_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_SLOW_QUERY_MS", "500")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.db_slow_query_ms == 500

    def test_log_uvicorn_access_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_UVICORN_ACCESS", "false")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.log_uvicorn_access is False

    def test_request_middleware_enabled_by_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.request_middleware_enabled is True

    def test_request_middleware_can_be_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OBSERVABILITY_REQUEST_MIDDLEWARE_ENABLED", "false")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.request_middleware_enabled is False

    def test_metrics_allowed_cidrs_default_is_loopback(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        cidrs = config.metrics_allowed_cidrs
        assert "127.0.0.0/8" in cidrs or any("127." in c for c in cidrs)

    def test_otlp_headers_not_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer topsecret")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert "topsecret" not in repr(config)


class TestPublishableConfigSkeleton:
    def test_config_skeleton_file_exists(self) -> None:
        from pathlib import Path

        import arvel

        # Lives in the app skeleton, not the workspace root — a top-level
        # `config/` package there shadows a consumer app's own `config` on sys.path.
        config_path = Path(arvel.__file__).parent / "_skeleton" / "config" / "observability.py"
        assert config_path.exists(), (
            "_skeleton/config/observability.py must exist (scaffolded into new apps)"
        )
