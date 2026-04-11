"""OpenTelemetry tracing bridge — optional dependency, no-op when not installed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from fastapi import FastAPI

    from arvel.observability.config import ObservabilitySettings


@runtime_checkable
class Tracer(Protocol):
    """Minimal tracer protocol — compatible with both OTEL and no-op tracers."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> Span: ...
    def start_span(self, name: str, **kwargs: Any) -> Span: ...


@runtime_checkable
class Span(Protocol):
    """Minimal span protocol — compatible with both OTEL and no-op spans."""

    def __enter__(self) -> Span: ...
    def __exit__(self, *args: Any) -> None: ...
    def set_attribute(self, key: str, value: Any) -> None: ...
    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None: ...


_HAS_OTEL = False
_HAS_OTEL_FASTAPI = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _HAS_OTEL = True
except ImportError:
    pass

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _HAS_OTEL_FASTAPI = True
except ImportError:
    pass


class _NoOpSpan:
    """Minimal no-op span for when OTEL is not installed."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpTracer:
    """No-op tracer satisfying the Tracer protocol."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


def configure_tracing(
    settings: ObservabilitySettings,
    *,
    app_name: str,
    fastapi_app: FastAPI | None = None,
) -> bool | None:
    """Configure OpenTelemetry tracing if enabled and installed.

    Returns True if OTEL was configured, None/False otherwise.
    """
    if not settings.otel_enabled:
        return None

    if not _HAS_OTEL:
        return False

    resource_name = settings.otel_service_name or app_name

    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": resource_name})
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            pass

    trace.set_tracer_provider(provider)

    if (
        fastapi_app is not None
        and _HAS_OTEL_FASTAPI
        and not getattr(fastapi_app.state, "_arvel_otel_instrumented", False)
    ):
        FastAPIInstrumentor.instrument_app(fastapi_app)
        fastapi_app.state._arvel_otel_instrumented = True

    return True


def get_tracer(name: str) -> Tracer:
    """Return an OTEL tracer or a no-op tracer if OTEL is not available."""
    if _HAS_OTEL:
        return cast("Tracer", trace.get_tracer(name))
    return _NoOpTracer()
