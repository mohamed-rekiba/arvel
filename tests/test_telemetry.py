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
    result = configure(exporter=exporter)  # explicit exporter forces setup even if disabled
    assert result is not None and result.tracer_provider is not None
    provider = result.tracer_provider
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
    settings.metrics = False  # traces-only: don't spin up real OTLP metric/log exporters
    settings.logs = False
    settings.sentry_dsn = "https://k@example.test/1"
    configure(settings, exporter=InMemorySpanExporter())
    assert captured["dsn"] == "https://k@example.test/1"


def test_signal_endpoint_derives_per_signal_paths() -> None:
    from arvel.telemetry import _signal_endpoint

    assert _signal_endpoint("http://h:4318/v1/traces", "metrics") == "http://h:4318/v1/metrics"
    assert _signal_endpoint("http://h:4318/v1/traces", "logs") == "http://h:4318/v1/logs"
    assert (
        _signal_endpoint("", "metrics") == ""
    )  # unset stays unset (exporter uses its own default)


def test_configure_exports_metrics() -> None:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    result = configure(metric_reader=reader)  # metrics-only setup (override forces it)
    assert result is not None and result.meter_provider is not None

    result.meter_provider.get_meter("test").create_counter("orders").add(3)
    data = reader.get_metrics_data()  # triggers collection
    metric_names = [
        m.name for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics
    ]
    assert "orders" in metric_names


def test_configure_exports_logs() -> None:
    import logging

    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

    exporter = InMemoryLogRecordExporter()
    result = configure(log_exporter=exporter)  # logs-only setup; auto-attaches a root handler
    assert result is not None and result.logger_provider is not None

    # Emit through stdlib logging — configure() attached the OTel handler to the root logger,
    # so records propagate to it and export (the real production behavior).
    log = logging.getLogger("arvel.telemetry.logtest")
    log.setLevel(logging.INFO)
    log.info("checkout-complete")
    result.logger_provider.force_flush()

    bodies = [r.log_record.body for r in exporter.get_finished_logs()]
    assert "checkout-complete" in bodies


def test_metric_reader_and_log_exporter_select_from_config() -> None:
    from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    from arvel.telemetry import _build_log_exporter, _build_metric_reader

    mem = TelemetrySettings()
    mem.exporter = "memory"
    assert isinstance(_build_metric_reader(mem), InMemoryMetricReader)

    console = TelemetrySettings()
    console.exporter = "console"
    assert isinstance(_build_log_exporter(console), ConsoleLogRecordExporter)


def test_arvel_log_facade_exports_to_otel_with_trace_context() -> None:
    """The gap-closer: arvel's public ``Log`` facade flows into OTel logs, correlated to the trace."""
    import structlog
    from opentelemetry import trace
    from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    import arvel.telemetry
    from arvel import Log
    from arvel.kernel import Application, set_application
    from arvel.kernel.logging import configure_logging
    from arvel.kernel.provider import KernelServiceProvider

    log_exporter = InMemoryLogRecordExporter()
    app = Application()
    KernelServiceProvider(app).register()  # bind "log" exactly as the framework does at boot
    set_application(app)
    try:
        configure_logging()  # arvel's structlog setup (as bootstrap does)
        result = configure(exporter=InMemorySpanExporter(), log_exporter=log_exporter)
        assert result is not None

        span = result.tracer_provider.get_tracer("t").start_span("checkout")
        with trace.use_span(span, end_on_exit=True):
            Log.info("payment-declined", order_id=42)  # the public facade an app actually calls
        result.logger_provider.force_flush()

        record = next(
            r.log_record
            for r in log_exporter.get_finished_logs()
            if r.log_record.body == "payment-declined"
        )
        assert record.attributes is not None and record.attributes.get("order_id") == 42
        assert record.trace_id == span.get_span_context().trace_id  # correlated to the trace
    finally:
        arvel.telemetry._otel_log_handler = None  # stop the bridge polluting later tests
        structlog.reset_defaults()
        set_application(None)


def test_tracer_helper_returns_a_usable_tracer() -> None:
    span_tracer = tracer("arvel.test")
    with span_tracer.start_as_current_span("unit"):
        pass  # no exception → a real tracer (no-op or configured)


def test_push_metric_reader_built_for_console_and_otlp() -> None:
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    from arvel.telemetry import _build_metric_reader

    console = TelemetrySettings()
    console.exporter = "console"
    assert isinstance(_build_metric_reader(console), PeriodicExportingMetricReader)

    otlp = TelemetrySettings()
    otlp.exporter = "otlp"
    otlp.endpoint = "http://h:4318/v1/traces"
    assert isinstance(_build_metric_reader(otlp), PeriodicExportingMetricReader)


def test_otlp_log_exporter_built() -> None:
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

    from arvel.telemetry import _build_log_exporter

    otlp = TelemetrySettings()
    otlp.exporter = "otlp"
    otlp.endpoint = "http://h:4318/v1/traces"
    assert isinstance(_build_log_exporter(otlp), OTLPLogExporter)


def test_span_helper_is_a_noop_when_tracing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.telemetry
    from arvel.telemetry import span

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    with span("work", kind="client", attributes={"x": 1}) as current:
        assert current is None  # off → yields None, no span, no opentelemetry work


def test_disabled_telemetry_does_no_opentelemetry_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """The 'off = free' guarantee: with telemetry off, the instrumentation helpers short-circuit to
    a no-op (a bool check + a no-op context manager) — they create no spans and touch no OTel state."""
    import arvel.telemetry
    from arvel.telemetry import span

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    ran = []
    with span("cache get", kind="client") as current:
        ran.append(current)  # the block still runs (transparent), just without a span
    assert ran == [None]
