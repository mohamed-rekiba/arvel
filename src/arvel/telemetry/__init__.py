"""arvel.telemetry — OpenTelemetry **traces, metrics & logs** wired from config (backend-agnostic via OTLP).

Configure the ``telemetry`` config section to export to **any** OTLP backend — Grafana
(Tempo for traces · Mimir/Prometheus for metrics · Loki for logs), Jaeger, Honeycomb, … — instead of a
single vendor. opentelemetry is imported lazily (the ``[telemetry]`` extra), and the whole thing is
**disabled by default** (a no-op until you opt in). Each signal can be toggled independently.

    # config/telemetry.py
    config = {"enabled": env("OTEL_ENABLED", False), "service_name": "blog",
              "endpoint": env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")}

Then, anywhere:  ``with tracer().start_as_current_span("checkout"): ...``  ·
``meter().create_counter("orders").add(1)``  ·  ``logging`` records export automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arvel.kernel import Settings


class TelemetrySettings(Settings):
    """Typed view over the ``telemetry`` config (DR-0016). ``exporter`` is ``otlp`` (production),
    ``console`` (dev), or ``memory`` (tests); ``endpoint`` is the OTLP/HTTP traces URL (the per-signal
    ``/v1/metrics`` and ``/v1/logs`` paths are derived from it). ``traces``/``metrics``/``logs`` toggle
    each signal."""

    __config_key__ = "telemetry"
    enabled: bool = False
    service_name: str = "arvel"
    exporter: str = "otlp"
    endpoint: str = ""
    traces: bool = True
    metrics: bool = True
    logs: bool = True
    sentry_dsn: str = ""


@dataclass
class Telemetry:
    """Handles to the providers :func:`configure` set up — ``None`` for any signal that's off."""

    tracer_provider: Any = None
    meter_provider: Any = None
    logger_provider: Any = None


def _signal_endpoint(endpoint: str, signal: str) -> str:
    """Map the traces OTLP URL to a sibling signal's path (``…/v1/traces`` → ``…/v1/metrics|logs``)."""
    if endpoint.endswith("/v1/traces"):
        return f"{endpoint[: -len('/v1/traces')]}/v1/{signal}"
    return endpoint


def _build_exporter(settings: TelemetrySettings) -> Any:
    """The OTel **span** exporter named by ``settings.exporter`` (lazy-imported)."""
    driver = settings.exporter
    if driver == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()
    if driver == "memory":
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        return InMemorySpanExporter()
    if driver == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = _signal_endpoint(settings.endpoint, "traces")
        return OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
    raise ValueError(f"Unknown telemetry exporter {driver!r} (expected: otlp, console, memory)")


def _build_metric_reader(settings: TelemetrySettings) -> Any:
    """The OTel **metric** reader named by ``settings.exporter`` (lazy-imported)."""
    driver = settings.exporter
    if driver == "memory":
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader

        return InMemoryMetricReader()
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    if driver == "console":
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

        return PeriodicExportingMetricReader(ConsoleMetricExporter())
    if driver == "otlp":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        endpoint = _signal_endpoint(settings.endpoint, "metrics")
        exporter = OTLPMetricExporter(endpoint=endpoint) if endpoint else OTLPMetricExporter()
        return PeriodicExportingMetricReader(exporter)
    raise ValueError(f"Unknown telemetry exporter {driver!r} (expected: otlp, console, memory)")


def _build_log_exporter(settings: TelemetrySettings) -> Any:
    """The OTel **log** exporter named by ``settings.exporter`` (lazy-imported)."""
    driver = settings.exporter
    if driver == "console":
        from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter

        return ConsoleLogRecordExporter()
    if driver == "memory":
        from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

        return InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]  # experimental logs API, no stubs
    if driver == "otlp":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        endpoint = _signal_endpoint(settings.endpoint, "logs")
        return OTLPLogExporter(endpoint=endpoint) if endpoint else OTLPLogExporter()
    raise ValueError(f"Unknown telemetry exporter {driver!r} (expected: otlp, console, memory)")


def configure(
    settings: TelemetrySettings | None = None,
    *,
    exporter: Any = None,
    metric_reader: Any = None,
    log_exporter: Any = None,
) -> Telemetry | None:
    """Set up the global OTel providers (traces/metrics/logs) from the ``telemetry`` config.

    A no-op (returns ``None``) when telemetry is disabled, unless an explicit exporter/reader is passed
    (tests). A signal is set up when it's enabled in config **or** its override is supplied. Returns a
    :class:`Telemetry` with the configured providers. Also inits Sentry when ``sentry_dsn`` is set.
    """
    settings = settings if settings is not None else TelemetrySettings()
    do_traces = (settings.enabled and settings.traces) or exporter is not None
    do_metrics = (settings.enabled and settings.metrics) or metric_reader is not None
    do_logs = (settings.enabled and settings.logs) or log_exporter is not None
    if not (do_traces or do_metrics or do_logs):
        return None

    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": settings.service_name})
    result = Telemetry()

    if do_traces:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter or _build_exporter(settings)))
        trace.set_tracer_provider(tracer_provider)  # honored once per process; later calls ignored
        result.tracer_provider = tracer_provider

    if do_metrics:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider

        reader = metric_reader or _build_metric_reader(settings)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
        result.meter_provider = meter_provider

    if do_logs:
        import logging
        import warnings

        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter or _build_log_exporter(settings))
        )
        set_logger_provider(logger_provider)
        # The SDK's LoggingHandler is deprecated in favor of opentelemetry-instrumentation-logging,
        # but we keep it to avoid pulling another dependency while the OTel logs API is still
        # experimental. Suppress just that one warning; revisit when logs stabilize.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            handler = LoggingHandler(logger_provider=logger_provider)
        logging.getLogger().addHandler(handler)
        result.logger_provider = logger_provider

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn)
    return result


def tracer(name: str = "arvel") -> Any:
    """An OpenTelemetry tracer for manual spans: ``with tracer().start_as_current_span("x"): ...``."""
    from opentelemetry import trace

    return trace.get_tracer(name)


def meter(name: str = "arvel") -> Any:
    """An OpenTelemetry meter for metrics: ``meter().create_counter("orders").add(1)``."""
    from opentelemetry import metrics

    return metrics.get_meter(name)


__all__ = ["Telemetry", "TelemetrySettings", "configure", "meter", "tracer"]
