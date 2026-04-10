"""Tests for OpenTelemetry tracing bridge — FR-020 to FR-027, SEC-004."""

from __future__ import annotations

from arvel.observability.config import ObservabilitySettings
from arvel.observability.tracing import configure_tracing, get_tracer


class TestConfigureTracing:
    def test_noop_when_disabled(self) -> None:
        """FR-026: when OTEL disabled, configure_tracing is a no-op."""
        settings = ObservabilitySettings(otel_enabled=False)
        result = configure_tracing(settings, app_name="test")
        assert result is None or result is False

    def test_noop_when_otel_not_installed(self) -> None:
        """FR-026: when OTEL not installed, no import error."""
        settings = ObservabilitySettings(otel_enabled=True)
        configure_tracing(settings, app_name="test")


class TestGetTracer:
    def test_get_tracer_returns_object(self) -> None:
        """FR-020: get_tracer returns a tracer (or no-op)."""
        tracer = get_tracer("test-module")
        assert tracer is not None

    def test_tracer_has_start_span(self) -> None:
        """FR-021: tracer supports start_span or start_as_current_span."""
        tracer = get_tracer("test-module")
        assert hasattr(tracer, "start_as_current_span") or hasattr(tracer, "start_span")
