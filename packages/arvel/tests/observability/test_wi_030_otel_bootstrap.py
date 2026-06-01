"""OTel SDK bootstrap."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def clean_otel_globals() -> Iterator[None]:
    """Reset OTel global providers after each test by patching internal state directly."""
    import opentelemetry._logs._internal as _logs_internal
    import opentelemetry.metrics._internal as _metrics_internal
    import opentelemetry.trace as _trace_mod

    # Save originals before the test modifies global state
    orig_trace = _trace_mod._TRACER_PROVIDER  # pyright: ignore[reportPrivateUsage]
    orig_logger = _logs_internal._LOGGER_PROVIDER  # pyright: ignore[reportPrivateUsage]
    orig_metrics = _metrics_internal._METER_PROVIDER  # pyright: ignore[reportPrivateUsage]

    yield

    # Reset guards so the restore doesn't hit "only set once" protection
    _trace_mod._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
    _logs_internal._LOGGER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
    _metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]

    _trace_mod._TRACER_PROVIDER = orig_trace  # pyright: ignore[reportPrivateUsage]
    _logs_internal._LOGGER_PROVIDER = orig_logger  # pyright: ignore[reportPrivateUsage]
    _metrics_internal._METER_PROVIDER = orig_metrics  # pyright: ignore[reportPrivateUsage]


class TestObservabilityServiceProviderExists:
    def test_provider_importable(self) -> None:
        from arvel.observability.provider import ObservabilityServiceProvider

        _ = ObservabilityServiceProvider

    def test_config_importable(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        _ = ObservabilityConfig

    def test_provider_is_service_provider(self) -> None:
        from arvel.observability.provider import ObservabilityServiceProvider
        from arvel.providers.service_provider import ServiceProvider

        assert issubclass(ObservabilityServiceProvider, ServiceProvider)


class TestObservabilityConfig:
    def test_config_reads_service_name_from_otel_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_SERVICE_NAME", "my-service")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.service_name == "my-service"

    def test_config_falls_back_to_app_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
        monkeypatch.setenv("APP_NAME", "my-app")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.service_name == "my-app"

    def test_config_otlp_endpoint_empty_by_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.otlp_endpoint == "" or config.otlp_endpoint is None

    def test_config_sdk_disabled_false_by_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.sdk_disabled is False

    def test_config_log_format_json_by_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.log_format == "json"

    def test_config_log_level_info_by_default(self) -> None:
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert config.log_level == "info"

    def test_config_otlp_headers_not_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer secret123")
        from arvel.observability.config import ObservabilityConfig

        config = ObservabilityConfig()
        assert "secret123" not in repr(config), "OTLP headers must not appear in repr"

    def test_invalid_log_level_raises_configuration_error(self) -> None:
        from arvel.config.exceptions import ConfigurationError
        from arvel.observability.config import ObservabilityConfig

        with pytest.raises((ConfigurationError, ValueError)):
            ObservabilityConfig.model_validate({"log_level": "notarealevel"})


class TestSDKBootstrap:
    def test_providers_registered_globally_after_boot(self) -> None:
        from arvel.observability.provider import ObservabilityServiceProvider
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider as SDKMeterProvider
        from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

        provider = ObservabilityServiceProvider.__new__(ObservabilityServiceProvider)
        # Boot without a real app — only tests provider registration
        provider.boot_providers()

        assert isinstance(trace.get_tracer_provider(), SDKTracerProvider)
        assert isinstance(metrics.get_meter_provider(), SDKMeterProvider)

    def test_sdk_disabled_skips_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from opentelemetry import trace
        from opentelemetry.trace import ProxyTracerProvider

        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        from arvel.observability.provider import ObservabilityServiceProvider

        provider = ObservabilityServiceProvider.__new__(ObservabilityServiceProvider)
        provider.boot_providers()

        # ProxyTracerProvider is the no-op global before SDK is set
        assert isinstance(trace.get_tracer_provider(), ProxyTracerProvider)

    def test_service_name_resource_attribute_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_SERVICE_NAME", "test-arvel")
        from arvel.observability.provider import ObservabilityServiceProvider
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

        provider = ObservabilityServiceProvider.__new__(ObservabilityServiceProvider)
        provider.boot_providers()

        tracer_provider = trace.get_tracer_provider()
        assert isinstance(tracer_provider, SDKTracerProvider)
        resource = tracer_provider.resource
        assert resource.attributes.get("service.name") == "test-arvel"

    def test_noop_exporter_used_when_no_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No connection errors when OTLP endpoint is not configured."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        from arvel.observability.provider import ObservabilityServiceProvider

        provider = ObservabilityServiceProvider.__new__(ObservabilityServiceProvider)
        # Should not raise
        provider.boot_providers()
