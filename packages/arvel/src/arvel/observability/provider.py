"""ObservabilityServiceProvider — bootstraps OTel providers and instrumentations."""

from __future__ import annotations

import opentelemetry._logs._internal as _logs_internal
import opentelemetry.metrics._internal as _metrics_internal
import opentelemetry.trace as _trace_mod
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from arvel.observability.config import ObservabilityConfig
from arvel.providers.service_provider import ServiceProvider


class ObservabilityServiceProvider(ServiceProvider):
    """Registers ObservabilityConfig and boots the OTel SDK on app start."""

    def register(self) -> None:
        c = self.container
        if not c.bound(ObservabilityConfig):
            c.instance(ObservabilityConfig, ObservabilityConfig())

    async def boot(self) -> None:
        config: ObservabilityConfig = self.container.make(ObservabilityConfig)
        self.boot_providers(config)

    def boot_providers(self, config: ObservabilityConfig | None = None) -> None:
        """Bootstrap OTel providers — callable without a full container for testing."""
        if config is None:
            config = ObservabilityConfig()
        if config.sdk_disabled:
            # Clear any previously installed SDK provider so callers see the
            # proxy (no-op) state — important when boot_providers() is called
            # more than once in the same process (e.g. in tests).
            _trace_mod._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
            _trace_mod._TRACER_PROVIDER = None  # pyright: ignore[reportPrivateUsage]
            return
        _bootstrap_otel(config)


def _bootstrap_otel(config: ObservabilityConfig) -> None:
    """Wire up OTel SDK providers, exporters, and auto-instrumentations."""
    resource = Resource.create({"service.name": config.service_name})

    # Tracer provider — bypass "set once" so boot() can be called in tests
    tracer_provider = TracerProvider(resource=resource)
    _attach_trace_exporters(tracer_provider, config)
    _trace_mod._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
    _trace_mod._TRACER_PROVIDER = tracer_provider  # pyright: ignore[reportPrivateUsage]

    # Logger provider
    log_provider = LoggerProvider(resource=resource)
    _attach_log_processors(log_provider, config)
    _logs_internal._LOGGER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
    _logs_internal._LOGGER_PROVIDER = log_provider  # pyright: ignore[reportPrivateUsage]

    # Always register a real MeterProvider; attach Prometheus reader only when enabled
    _bootstrap_metrics(config, resource)

    # Uvicorn log bridge
    from arvel.observability.uvicorn_bridge import install_uvicorn_bridge

    install_uvicorn_bridge()

    # SQLAlchemy auto-instrumentation
    if config.db_query_log_enabled:
        try:
            from opentelemetry.instrumentation.sqlalchemy import (  # pyright: ignore[reportMissingTypeStubs]
                SQLAlchemyInstrumentor,
            )

            SQLAlchemyInstrumentor().instrument()
        except ImportError:
            pass


def _attach_trace_exporters(provider: TracerProvider, config: ObservabilityConfig) -> None:
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # No collector: don't dump spans to stdout — they're noise next to the logs.
    # The http.request log already carries duration + trace context for correlation.
    if not config.otlp_endpoint:
        return

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(
            endpoint=config.otlp_endpoint,
            headers=_parse_headers(config.otlp_headers.get_secret_value()),
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except ImportError:
        pass


def _attach_log_processors(provider: LoggerProvider, config: ObservabilityConfig) -> None:
    from opentelemetry.sdk._logs.export import (
        BatchLogRecordProcessor,
        ConsoleLogRecordExporter,
        SimpleLogRecordProcessor,
    )

    if not config.otlp_endpoint:
        # No collector: render one clean line per record to stdout. Simple (not
        # batch) so logs show up immediately in dev. Without this, json format
        # would attach no exporter at all and every log line would vanish.
        # Bind out=sys.stdout at attach time — the exporter's default captures
        # stdout once at import, which breaks under reassignment (e.g. tests).
        import sys

        from arvel.observability.stdout_log_exporter import formatter_for

        stdout_exporter = ConsoleLogRecordExporter(
            out=sys.stdout, formatter=formatter_for(config.log_format)
        )
        provider.add_log_record_processor(SimpleLogRecordProcessor(stdout_exporter))
        return

    try:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
            OTLPLogExporter,
        )

        exporter = OTLPLogExporter(
            endpoint=config.otlp_endpoint,
            headers=_parse_headers(config.otlp_headers.get_secret_value()),
        )
        provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    except ImportError:
        pass


def _bootstrap_metrics(config: ObservabilityConfig, resource: Resource) -> None:
    readers: list[object] = []
    if config.metrics_enabled:
        from opentelemetry.exporter.prometheus import PrometheusMetricReader

        readers.append(PrometheusMetricReader())

    meter_provider = MeterProvider(resource=resource, metric_readers=readers)  # type: ignore[arg-type]

    # Bypass "set once" guard so providers can be re-configured (e.g. in tests)
    _metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
    _metrics_internal._METER_PROVIDER = meter_provider  # pyright: ignore[reportPrivateUsage]


def _parse_headers(raw: str) -> dict[str, str]:
    """Parse ``key=value,key2=value2`` header string into a dict."""
    if not raw:
        return {}
    result: dict[str, str] = {}
    for raw_pair in raw.split(","):
        pair = raw_pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
    return result


__all__ = ["ObservabilityServiceProvider"]
