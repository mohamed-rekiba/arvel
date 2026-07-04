"""Telemetry's unit tests use an in-memory exporter; this proves the real OTLP/HTTP export path end
to end against a live OpenTelemetry Collector.
"""

from __future__ import annotations

import time
import uuid

import pytest

from arvel.kernel import Application, set_application
from arvel.telemetry import configure

pytestmark = pytest.mark.integration


def test_span_reaches_a_real_otlp_collector(otel_collector: object) -> None:
    span_name = f"arvel-otel-{uuid.uuid4().hex[:8]}"
    host = otel_collector.get_container_host_ip()  # type: ignore[attr-defined]
    port = otel_collector.get_exposed_port(4318)  # type: ignore[attr-defined]

    app = Application()
    app.make("config").set(
        "telemetry",
        {
            "enabled": True,
            "exporter": "otlp",
            "endpoint": f"http://{host}:{port}/v1/traces",
            "service_name": "arvel-otel-itest",
        },
    )
    set_application(app)
    try:
        result = configure()
        assert result is not None and result.tracer_provider is not None, "tracing not configured"
        # emit on the configured provider directly — OTel's global set-tracer-provider is once-per-process
        with result.tracer_provider.get_tracer("itest").start_as_current_span(span_name):
            pass
        assert result.tracer_provider.force_flush() is True
    finally:
        set_application(None)

    received = False
    for _ in range(40):  # up to ~10s for the collector to log the export
        out, err = otel_collector.get_logs()  # type: ignore[attr-defined]
        if span_name in out.decode(errors="ignore") + err.decode(errors="ignore"):
            received = True
            break
        time.sleep(0.25)
    assert received, f"collector did not receive span {span_name!r} via OTLP/HTTP"
