"""arvel.telemetry — OpenTelemetry **traces, metrics & logs** wired from config (backend-agnostic via OTLP).

Configure the ``telemetry`` config section to export to **any** OTLP backend — Grafana
(Tempo for traces · Mimir/Prometheus for metrics · Loki for logs), Jaeger, Honeycomb, … — instead of a
single vendor. opentelemetry is imported lazily (the ``[telemetry]`` extra), and the whole thing is
**disabled by default** (a no-op until you opt in). Each signal can be toggled independently.

    # config/telemetry.py
    config = {"enabled": env("OTEL_ENABLED", False), "service_name": "blog",
              "endpoint": env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")}

Then, anywhere:  ``with tracer().start_as_current_span("checkout"): ...``  ·
``meter().create_counter("orders").add(1)``  ·  ``Log`` records export automatically, correlated to
the active trace.
"""

from __future__ import annotations

import contextlib
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
    prometheus: bool = (
        False  # metrics delivery: False = OTLP push; True = pull via a /metrics route
    )
    sentry_dsn: str = ""


@dataclass
class Telemetry:
    """Handles to the providers :func:`configure` set up — ``None`` for any signal that's off."""

    tracer_provider: Any = None
    meter_provider: Any = None
    logger_provider: Any = None


# Set true once configure() wires tracing. Lets the HTTP middleware skip all OpenTelemetry work
# (and imports) on a request when tracing is off — checking this costs nothing.
_tracing_enabled = False

# Set true once configure() wires metrics — same idea, for the HTTP request-metrics path.
_metrics_enabled = False

# The OTel logging handler configure() builds — the structlog bridge feeds records to it directly.
_otel_log_handler: Any = None


def is_tracing_enabled() -> bool:
    """Whether :func:`configure` has set up tracing — a cheap gate that imports no opentelemetry."""
    return _tracing_enabled


def is_metrics_enabled() -> bool:
    """Whether :func:`configure` has set up metrics — a cheap gate that imports no opentelemetry."""
    return _metrics_enabled


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
    """The OTel **metric** reader. ``prometheus`` → a pull reader (scraped at ``/metrics``); otherwise
    the push reader named by ``settings.exporter`` (lazy-imported)."""
    if settings.prometheus:
        from opentelemetry.exporter.prometheus import PrometheusMetricReader

        return PrometheusMetricReader()
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
        tracer_provider.add_span_processor(
            BatchSpanProcessor(exporter or _build_exporter(settings))
        )
        trace.set_tracer_provider(tracer_provider)  # honored once per process; later calls ignored
        result.tracer_provider = tracer_provider
        global _tracing_enabled
        _tracing_enabled = True

    if do_metrics:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider

        reader = metric_reader or _build_metric_reader(settings)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
        result.meter_provider = meter_provider
        global _metrics_enabled
        _metrics_enabled = True

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
        logging.getLogger().addHandler(handler)  # captures stdlib logging users
        global _otel_log_handler
        _otel_log_handler = handler
        instrument_logging()  # route arvel's Log (structlog) into OTel too, with trace context
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


@contextlib.contextmanager
def span(name: str, *, kind: str = "internal", attributes: dict[str, Any] | None = None) -> Any:
    """Open a gated OpenTelemetry span around a block — a no-op (yields ``None``, imports no
    opentelemetry) when tracing is off. ``kind`` is internal|client|server|consumer|producer. Sets
    ERROR status + records the exception if the block raises. Used to instrument library calls
    (cache, the HTTP client, …) consistently."""
    if not is_tracing_enabled():
        yield None
        return
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    span_kind = {
        "client": SpanKind.CLIENT,
        "server": SpanKind.SERVER,
        "consumer": SpanKind.CONSUMER,
        "producer": SpanKind.PRODUCER,
        "internal": SpanKind.INTERNAL,
    }.get(kind, SpanKind.INTERNAL)
    with trace.get_tracer("arvel").start_as_current_span(name, kind=span_kind) as current:
        for key, value in (attributes or {}).items():
            current.set_attribute(key, value)
        try:
            yield current
        except Exception as exc:
            current.set_status(Status(StatusCode.ERROR))
            current.record_exception(exc)
            raise


async def prometheus_metrics(request: Any = None) -> Any:
    """Route handler for a Prometheus scrape endpoint — returns the current metrics in the exposition
    format. ``TelemetryServiceProvider`` registers it at ``/metrics`` when ``telemetry.prometheus`` is
    on (the ``PrometheusMetricReader`` exposes the OTel metrics through the prometheus_client registry)."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from arvel.http.response import Response

    return Response(content=generate_latest(), headers={"content-type": CONTENT_TYPE_LATEST})


# stdlib level per structlog method name, so the OTel handler maps severity correctly.
_LOG_LEVELS = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
    "exception": 40,
}
# event-dict keys not worth duplicating as OTel attributes (the body, plus renderer-added fields).
_SKIP_LOG_KEYS = frozenset({"event", "level", "timestamp"})


def _otel_log_processor(
    _logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor: mirror each log event into OpenTelemetry — the OTel handler stamps the
    active span's trace_id/span_id, so logs correlate to their trace — then return the event unchanged
    so the normal console/JSON renderer still runs (stdout is unaffected)."""
    handler = _otel_log_handler
    if handler is not None:
        import logging

        level = _LOG_LEVELS.get(method_name, logging.INFO)
        record = logging.LogRecord(
            "arvel", level, "(structlog)", 0, str(event_dict.get("event", "")), None, None
        )
        for key, value in event_dict.items():
            if key not in _SKIP_LOG_KEYS:
                setattr(
                    record, key, value if isinstance(value, (str, int, float, bool)) else str(value)
                )
        handler.handle(record)
    return event_dict


_otel_log_processor._arvel_otel = True  # type: ignore[attr-defined]  # marker for idempotent insertion


def instrument_logging() -> None:
    """Insert the OTel-forwarding processor into structlog's chain, just before the renderer. A no-op
    until the OTel log handler exists (telemetry off → zero overhead) and idempotent (no double-emit).

    Called from both ``configure()`` and arvel's ``configure_logging()``, so the bridge survives
    whichever runs last — ``configure_logging`` rebuilds structlog's processor list and would otherwise
    drop it."""
    if _otel_log_handler is None:
        return
    import structlog

    processors = list(structlog.get_config().get("processors", []))
    if any(getattr(processor, "_arvel_otel", False) for processor in processors):
        return
    processors.insert(max(len(processors) - 1, 0), _otel_log_processor)  # before the final renderer
    structlog.configure(processors=processors)


__all__ = [
    "Telemetry",
    "TelemetrySettings",
    "configure",
    "is_metrics_enabled",
    "is_tracing_enabled",
    "meter",
    "prometheus_metrics",
    "span",
    "tracer",
]
