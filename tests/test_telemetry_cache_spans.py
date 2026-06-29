"""Cache auto-instrumentation: get/put/forget/increment emit CLIENT spans when tracing is on; get
records cache.hit; a no-op when tracing is off."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.cache import CacheRepository
from arvel.telemetry import configure


class _FakeClient:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, expire: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def incr(self, key: str, by: int) -> int:
        self.store[key] = self.store.get(key, 0) + by
        return self.store[key]


def _capture_spans() -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    configure(exporter=InMemorySpanExporter())
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_cache_ops_emit_client_spans() -> None:
    from opentelemetry.trace import SpanKind

    exporter = _capture_spans()
    cache = CacheRepository(_FakeClient())
    await cache.put("greeting", "hi")
    await cache.get("greeting")
    await cache.get("absent")
    await cache.forget("greeting")
    await cache.increment("hits")

    spans = {s.name: s for s in exporter.get_finished_spans()}
    for name in ("cache put", "cache get", "cache forget", "cache increment"):
        assert name in spans, name
    assert spans["cache get"].kind == SpanKind.CLIENT

    gets = [s for s in exporter.get_finished_spans() if s.name == "cache get"]
    assert any(s.attributes["cache.hit"] is True for s in gets)  # the hit
    assert any(s.attributes["cache.hit"] is False for s in gets)  # the miss


async def test_no_span_and_value_unchanged_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import arvel.telemetry

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    cache = CacheRepository(_FakeClient())
    await cache.put("k", "v")
    assert await cache.get("k") == "v"  # transparent
    assert await cache.get("x", "fallback") == "fallback"
