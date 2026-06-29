"""Outbound HTTP client auto-instrumentation: each request emits a CLIENT span and injects the W3C
traceparent into the outgoing headers, so the callee continues the same distributed trace."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from arvel.client import PendingRequest
from arvel.telemetry import configure


def _capture_spans() -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    configure(exporter=InMemorySpanExporter())
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_request_emits_client_span_and_propagates_traceparent() -> None:
    from opentelemetry.trace import SpanKind

    exporter = _capture_spans()
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["traceparent"] = request.headers.get("traceparent")
        return httpx.Response(200, json={"ok": True})

    client = PendingRequest(transport=httpx.MockTransport(handler))
    response = await client.request("GET", "http://service.test/data")

    assert response.status_code == 200
    span = next(s for s in exporter.get_finished_spans() if s.name == "HTTP GET")
    assert span.kind == SpanKind.CLIENT
    assert span.attributes["http.request.method"] == "GET"
    assert span.attributes["http.response.status_code"] == 200
    assert seen["traceparent"] is not None  # context propagated to the callee
    assert format(span.context.trace_id, "032x") in seen["traceparent"]  # same trace


async def test_4xx_marks_span_error() -> None:
    from opentelemetry.trace import StatusCode

    exporter = _capture_spans()
    transport = httpx.MockTransport(lambda req: httpx.Response(404))
    client = PendingRequest(transport=transport)
    await client.request("GET", "http://service.test/missing")

    span = next(s for s in exporter.get_finished_spans() if s.name == "HTTP GET")
    assert span.attributes["http.response.status_code"] == 404
    assert span.status.status_code == StatusCode.ERROR


async def test_no_span_when_tracing_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.telemetry

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["traceparent"] = request.headers.get("traceparent")
        return httpx.Response(200)

    client = PendingRequest(transport=httpx.MockTransport(handler))
    response = await client.request("GET", "http://service.test/data")
    assert response.status_code == 200          # transparent
    assert seen["traceparent"] is None          # no injection when off
