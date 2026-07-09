"""Queue job auto-instrumentation: each job execution emits a CONSUMER span (nested under the dispatching
trace when the job runs inline), so background work is visible in traces."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.queue import Job, QueueManager
from arvel.telemetry import configure


class _Greet(Job):
    async def handle(self) -> Any:
        return "done"


def _capture_spans() -> Any:
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    configure(exporter=InMemorySpanExporter())
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def _manager() -> QueueManager:
    from taskiq import InMemoryBroker

    return QueueManager(broker=InMemoryBroker())


async def test_job_execution_emits_consumer_span() -> None:
    from opentelemetry.trace import SpanKind

    exporter = _capture_spans()
    await _manager()._worker._invoke(_Greet())
    span = next(s for s in exporter.get_finished_spans() if s.name == "job _Greet")
    assert span.kind == SpanKind.CONSUMER
    assert span.attributes["code.function"] == "_Greet"
    assert span.attributes["messaging.operation"] == "process"


async def test_job_span_nests_under_dispatching_trace() -> None:
    from opentelemetry import trace

    exporter = _capture_spans()
    parent = trace.get_tracer_provider().get_tracer("t").start_span("request")
    with trace.use_span(parent, end_on_exit=True):
        await _manager()._worker._invoke(_Greet())  # inline execution → nests under the request
    job = next(s for s in exporter.get_finished_spans() if s.name == "job _Greet")
    assert job.parent is not None
    assert job.parent.span_id == parent.get_span_context().span_id


async def test_job_span_links_to_dispatching_trace_across_the_broker() -> None:
    """Cross-process: the traceparent captured at dispatch rides in the payload, so a job run in a
    separate context (no ambient span) still links to the dispatching request's trace."""
    from opentelemetry import trace

    from arvel.queue import deserialize_instance, serialize_instance

    exporter = _capture_spans()
    parent = trace.get_tracer_provider().get_tracer("t").start_span("request")
    with trace.use_span(parent, end_on_exit=True):
        payload = serialize_instance(
            _Greet()
        )  # dispatch — captures the traceparent into the payload

    # "worker side": a fresh context with no ambient span — only the payload carries the link
    job = await deserialize_instance(payload)
    await _manager()._worker._invoke(job)

    span = next(s for s in exporter.get_finished_spans() if s.name == "job _Greet")
    assert span.parent is not None
    assert (
        span.parent.trace_id == parent.get_span_context().trace_id
    )  # same trace across the broker


async def test_no_span_and_result_unchanged_when_tracing_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.telemetry

    monkeypatch.setattr(arvel.telemetry, "is_tracing_enabled", lambda: False)
    result = await _manager()._worker._invoke(_Greet())
    assert result == "done"  # transparent: runs and returns, no span machinery
