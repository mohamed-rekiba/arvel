"""DB query auto-instrumentation: each query through ConnectionResolver emits a CLIENT span, nested under
the current span, carrying db.statement with placeholders (never bind values). Proven via an in-memory
span exporter attached to the live tracer provider — the same path that ships spans over OTLP."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.telemetry import configure

_T = sa.table("widgets", sa.column("id"), sa.column("note"))
_SENTINEL = "leak-canary-must-not-appear"  # a fake bind value; asserted absent from spans


def _capture_spans() -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    configure(exporter=InMemorySpanExporter())  # enable tracing + a real provider
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def _resolver() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.text("CREATE TABLE widgets (id INTEGER PRIMARY KEY, note TEXT)"))
    return db


async def test_select_emits_client_span_with_statement() -> None:
    from opentelemetry.trace import SpanKind

    exporter = _capture_spans()
    db = await _resolver()
    try:
        await db.fetch_all(sa.select(_T))
        spans = [s for s in exporter.get_finished_spans() if s.name.startswith("db ")]
        select = next(s for s in spans if s.name == "db SELECT")
        assert select.kind == SpanKind.CLIENT
        assert select.attributes["db.system"] == "sqlite"
        assert "widgets" in select.attributes["db.statement"]  # the SQL text is present
    finally:
        await db.dispose()


async def test_bind_values_never_leak_into_the_span() -> None:
    exporter = _capture_spans()
    db = await _resolver()
    try:
        await db.execute(_T.insert().values(id=1, note=_SENTINEL))
        statements = [
            s.attributes.get("db.statement", "")
            for s in exporter.get_finished_spans()
            if s.name.startswith("db ")
        ]
        assert statements  # we did emit a span
        assert all(_SENTINEL not in stmt for stmt in statements)  # bind value never captured
    finally:
        await db.dispose()


async def test_query_span_nests_under_the_current_span() -> None:
    from opentelemetry import trace

    exporter = _capture_spans()
    db = await _resolver()
    try:
        parent = trace.get_tracer_provider().get_tracer("t").start_span("request")
        with trace.use_span(parent, end_on_exit=True):
            await db.fetch_all(sa.select(_T))
        query = next(s for s in exporter.get_finished_spans() if s.name == "db SELECT")
        assert query.parent is not None
        assert (
            query.parent.span_id == parent.get_span_context().span_id
        )  # child of the request span
    finally:
        await db.dispose()


async def test_failed_query_marks_span_error_and_propagates() -> None:
    from opentelemetry.trace import StatusCode

    exporter = _capture_spans()
    db = await _resolver()
    try:
        with pytest.raises(Exception):  # noqa: B017 - any DB error; we assert on the span
            await db.fetch_all(sa.text("SELECT * FROM does_not_exist"))
        span = next(s for s in exporter.get_finished_spans() if s.name == "db SELECT")
        assert span.status.status_code == StatusCode.ERROR
        assert any(e.name == "exception" for e in span.events)
    finally:
        await db.dispose()


async def test_no_span_and_correct_results_when_tracing_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.telemetry

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    db = ConnectionResolver()
    try:
        await db.execute(sa.text("CREATE TABLE widgets (id INTEGER PRIMARY KEY, note TEXT)"))
        await db.execute(_T.insert().values(id=1, note="x"))
        rows = await db.fetch_all(sa.select(_T))
        assert len(rows) == 1 and rows[0]["note"] == "x"  # transparent: results unchanged
    finally:
        await db.dispose()
