"""arvel.telemetry — OpenTelemetry tracing wired from config (backend-agnostic via OTLP).

Configure the ``telemetry`` config section to export traces to **any** OTLP backend — Grafana
(Tempo/Alloy), Jaeger, Honeycomb, … — instead of a single vendor. opentelemetry is imported lazily
(the ``[telemetry]`` extra), and the whole thing is **disabled by default** (a no-op until you opt in).

    # config/telemetry.py
    config = {"enabled": env("OTEL_ENABLED", False), "service_name": "blog",
              "endpoint": env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")}

Then, anywhere:  ``with tracer().start_as_current_span("checkout"): ...``
"""

from __future__ import annotations

from typing import Any

from arvel.kernel import Settings


class TelemetrySettings(Settings):
    """Typed view over the ``telemetry`` config (DR-0016). ``exporter`` is ``otlp`` (production),
    ``console`` (dev), or ``memory`` (tests); ``endpoint`` is the OTLP/HTTP URL for ``otlp``."""

    __config_key__ = "telemetry"
    enabled: bool = False
    service_name: str = "arvel"
    exporter: str = "otlp"
    endpoint: str = ""
    sentry_dsn: str = ""


def _build_exporter(settings: TelemetrySettings) -> Any:
    """The OTel span exporter named by ``settings.exporter`` (lazy-imported)."""
    driver = settings.exporter
    if driver == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()
    if driver == "memory":
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        return InMemorySpanExporter()
    if driver == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=settings.endpoint) if settings.endpoint else OTLPSpanExporter()
    raise ValueError(f"Unknown telemetry exporter {driver!r} (expected: otlp, console, memory)")


def configure(settings: TelemetrySettings | None = None, *, exporter: Any = None) -> Any:
    """Set up the global OTel tracer provider with a span exporter, from the ``telemetry`` config.

    A no-op (returns ``None``) when telemetry is disabled, unless an explicit ``exporter`` is passed
    (tests). Returns the configured ``TracerProvider``. Also inits Sentry when ``sentry_dsn`` is set.
    """
    settings = settings if settings is not None else TelemetrySettings()
    if not settings.enabled and exporter is None:
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
    provider.add_span_processor(BatchSpanProcessor(exporter or _build_exporter(settings)))
    trace.set_tracer_provider(provider)  # honored once per process; later calls are ignored by OTel

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn)
    return provider


def tracer(name: str = "arvel") -> Any:
    """An OpenTelemetry tracer for manual spans: ``with tracer().start_as_current_span("x"): ...``."""
    from opentelemetry import trace

    return trace.get_tracer(name)


__all__ = ["TelemetrySettings", "configure", "tracer"]
