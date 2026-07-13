"""TelemetryMiddleware — every request becomes an OpenTelemetry SERVER span (with W3C context
propagation), and a no-op passthrough when tracing is off. Spans are captured via an in-memory
exporter attached to the live tracer provider (the same path that ships them over OTLP)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from arvel.telemetry import configure
from arvel.telemetry.middleware import TelemetryMiddleware


class FakeRequest:
    def __init__(
        self, method: str = "GET", path: str = "/orders", headers: dict[str, str] | None = None
    ):
        self._method = method
        self._path = path
        self.raw = SimpleNamespace(headers=headers or {})

    def method(self) -> str:
        return self._method

    def path(self) -> str:
        return self._path


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


def _capture_spans() -> Any:
    """Enable tracing and attach an in-memory exporter to the live (global) tracer provider."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    configure(exporter=InMemorySpanExporter())  # ensures tracing is on + a real provider is set
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_passthrough_when_telemetry_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.telemetry

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    monkeypatch.setattr(arvel.telemetry, "is_metrics_enabled", lambda: False)
    seen = []

    async def destination(req: Any) -> str:
        seen.append(req)
        return "ok"

    result = await TelemetryMiddleware().handle(FakeRequest(), destination)
    assert result == "ok" and len(seen) == 1  # called through, no span/metric machinery


async def test_records_http_request_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    import arvel.telemetry

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)  # metrics-only path
    monkeypatch.setattr(arvel.telemetry, "is_metrics_enabled", lambda: True)
    monkeypatch.setattr(arvel.telemetry, "meter", lambda name="arvel": provider.get_meter(name))

    await _run(TelemetryMiddleware(), FakeRequest("GET", "/orders"), FakeResponse(200))

    metrics = {
        m.name: m
        for rm in reader.get_metrics_data().resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert "http.server.request.count" in metrics
    assert "http.server.request.duration" in metrics
    point = next(iter(metrics["http.server.request.count"].data.data_points))
    assert point.value == 1
    assert point.attributes["http.request.method"] == "GET"
    assert point.attributes["http.response.status_code"] == 200


async def _run(mw: TelemetryMiddleware, request: FakeRequest, response: FakeResponse) -> None:
    """Mirror the kernel: handle() opens the span, terminate() closes it with the normalized response."""

    async def destination(req: Any) -> FakeResponse:
        return response

    await mw.handle(request, destination)
    await mw.terminate(request, response)


async def test_creates_server_span_with_http_attributes() -> None:
    from opentelemetry.trace import SpanKind

    exporter = _capture_spans()
    await _run(TelemetryMiddleware(), FakeRequest("POST", "/orders"), FakeResponse(201))

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "POST /orders" in spans
    span = spans["POST /orders"]
    assert span.kind == SpanKind.SERVER
    assert span.attributes["http.request.method"] == "POST"
    assert span.attributes["url.path"] == "/orders"
    assert span.attributes["http.response.status_code"] == 201  # real status, from terminate()


async def test_continues_upstream_trace_context() -> None:
    exporter = _capture_spans()
    upstream = "0af7651916cd43dd8448eb211c80319c"
    headers = {"traceparent": f"00-{upstream}-b7ad6b7169203331-01"}

    await _run(TelemetryMiddleware(), FakeRequest(headers=headers), FakeResponse(200))

    span = next(s for s in exporter.get_finished_spans() if s.name == "GET /orders")
    assert span.context.trace_id == int(upstream, 16)  # same distributed trace as the caller


async def test_marks_server_error_as_error_status() -> None:
    from opentelemetry.trace import StatusCode

    exporter = _capture_spans()
    await _run(TelemetryMiddleware(), FakeRequest(path="/boom"), FakeResponse(500))

    span = next(s for s in exporter.get_finished_spans() if s.name == "GET /boom")
    assert span.attributes["http.response.status_code"] == 500
    assert span.status.status_code == StatusCode.ERROR


async def test_handler_exception_ends_span_with_error() -> None:
    from opentelemetry.trace import StatusCode

    exporter = _capture_spans()

    async def boom(req: Any) -> Any:
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        await TelemetryMiddleware().handle(FakeRequest(path="/explode"), boom)
    # terminate is not run on the exception path; handle() must have ended the span itself
    span = next(s for s in exporter.get_finished_spans() if s.name == "GET /explode")
    assert span.status.status_code == StatusCode.ERROR
    assert any(e.name == "exception" for e in span.events)
