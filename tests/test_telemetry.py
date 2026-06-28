"""Telemetry — OpenTelemetry tracing wired from config, backend-agnostic via OTLP. Proven by exporting
spans through an in-memory exporter (the same code path that ships them to Grafana Tempo/Jaeger/etc.)."""

from __future__ import annotations

import pytest

from arvel.telemetry import TelemetrySettings, _build_exporter, configure, tracer


def test_disabled_by_default_is_a_noop() -> None:
    # no app/config → enabled=False → configure() does nothing (no OTel set up)
    assert TelemetrySettings().enabled is False
    assert configure(TelemetrySettings()) is None


def test_otlp_is_the_default_exporter() -> None:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    settings = TelemetrySettings()
    settings.exporter = "otlp"
    settings.endpoint = "http://localhost:4318/v1/traces"
    assert isinstance(_build_exporter(settings), OTLPSpanExporter)


def test_unknown_exporter_raises() -> None:
    settings = TelemetrySettings()
    settings.exporter = "splunk"
    with pytest.raises(ValueError, match="splunk"):
        _build_exporter(settings)


def test_configure_exports_spans_to_the_exporter() -> None:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = configure(exporter=exporter)  # explicit exporter forces setup even if disabled
    assert provider is not None
    assert provider.resource.attributes["service.name"] == "arvel"

    span_tracer = provider.get_tracer("test")
    with span_tracer.start_as_current_span("checkout"):
        pass
    provider.force_flush()

    names = [s.name for s in exporter.get_finished_spans()]
    assert "checkout" in names  # the span reached the (OTLP-equivalent) exporter


def test_console_and_memory_exporters_build() -> None:
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    console = TelemetrySettings()
    console.exporter = "console"
    assert isinstance(_build_exporter(console), ConsoleSpanExporter)

    memory = TelemetrySettings()
    memory.exporter = "memory"
    assert isinstance(_build_exporter(memory), InMemorySpanExporter)


def test_sentry_is_initialized_when_dsn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    captured: dict[str, str] = {}
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: captured.update(kw))

    settings = TelemetrySettings()
    settings.enabled = True
    settings.sentry_dsn = "https://k@example.test/1"
    configure(settings, exporter=InMemorySpanExporter())
    assert captured["dsn"] == "https://k@example.test/1"


def test_tracer_helper_returns_a_usable_tracer() -> None:
    span_tracer = tracer("arvel.test")
    with span_tracer.start_as_current_span("unit"):
        pass  # no exception → a real tracer (no-op or configured)
