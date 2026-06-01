"""Stdout log formatting + no-endpoint exporter wiring."""

from __future__ import annotations

import json

import pytest
from arvel.observability.stdout_log_exporter import (
    format_console,
    format_json,
    format_span_console,
    formatter_for,
)
from opentelemetry._logs import LogRecord as OtelLogRecord
from opentelemetry._logs import get_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, ReadableLogRecord
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def _capture(
    *,
    body: str = "route.registered",
    level: str = "INFO",
    logger: str = "arvel",
    attributes: dict[str, str] | None = None,
    in_span: bool = False,
) -> ReadableLogRecord:
    """Emit one record through a real provider and return the readable record."""
    provider = LoggerProvider(resource=Resource.create({"service.name": "test"}))
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call] # OTel SDK lacks py.typed
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    log = provider.get_logger(logger)

    def emit() -> None:
        log.emit(OtelLogRecord(body=body, severity_text=level, attributes=attributes or {}))

    if in_span:
        with TracerProvider().get_tracer("test").start_as_current_span("span"):
            emit()
    else:
        emit()

    provider.force_flush()
    return exporter.get_finished_logs()[0]


class TestJsonFormat:
    def test_single_line_valid_json(self) -> None:
        out = format_json(_capture(attributes={"path": "/api/products", "method": "GET"}))
        assert out.endswith("\n")
        assert out.count("\n") == 1
        payload = json.loads(out)
        assert payload["message"] == "route.registered"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "arvel"
        assert payload["path"] == "/api/products"
        assert payload["method"] == "GET"

    def test_includes_trace_ids_when_in_span(self) -> None:
        payload = json.loads(format_json(_capture(in_span=True)))
        assert len(payload["trace_id"]) == 32
        assert len(payload["span_id"]) == 16

    def test_user_attribute_cannot_shadow_message(self) -> None:
        # An attribute named "message" must not overwrite the log body.
        payload = json.loads(format_json(_capture(attributes={"message": "evil"})))
        assert payload["message"] == "route.registered"


class TestConsoleFormat:
    def test_human_readable_line(self) -> None:
        out = format_console(_capture(level="INFO", attributes={"service": "db"}))
        assert out.endswith("\n")
        assert "INFO" in out
        assert "arvel" in out
        assert "route.registered" in out
        assert "service=db" in out

    def test_no_suffix_without_attributes(self) -> None:
        out = format_console(_capture(attributes={}))
        assert out.rstrip("\n").endswith("route.registered")


class TestSpanFormat:
    def test_single_readable_line(self) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        with provider.get_tracer("test").start_as_current_span("db.query") as span:
            span.set_attribute("db.statement", "SELECT 1")

        out = format_span_console(exporter.get_finished_spans()[0])
        assert out.endswith("\n")
        assert out.count("\n") == 1
        assert "TRACE" in out
        assert "db.query" in out
        assert "dur=" in out
        assert "trace_id=" in out
        assert "db.statement=SELECT 1" in out


class TestFormatterFor:
    def test_console_selected(self) -> None:
        assert formatter_for("console") is format_console

    def test_json_is_default(self) -> None:
        assert formatter_for("json") is format_json
        assert formatter_for("anything-else") is format_json


class TestNoEndpointWiring:
    """Without a collector, logs must still reach stdout — otherwise every line
    vanishes (the bug this fixes). capfd (fd-level) sees the exporter's stdout
    writes regardless of pytest's Python-level capture.
    """

    @pytest.mark.parametrize(
        ("fmt", "needle"),
        [("console", "service=db"), ("json", '"service":"db"')],
    )
    def test_logs_reach_stdout_without_collector(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
        fmt: str,
        needle: str,
    ) -> None:
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.setenv("LOG_FORMAT", fmt)
        from arvel.observability.config import ObservabilityConfig
        from arvel.observability.provider import ObservabilityServiceProvider

        provider = ObservabilityServiceProvider.__new__(ObservabilityServiceProvider)
        provider.boot_providers(ObservabilityConfig())

        get_logger_provider().get_logger("arvel").emit(
            OtelLogRecord(
                body="service.connected",
                severity_text="INFO",
                attributes={"service": "db"},
            )
        )

        out = capfd.readouterr().out
        assert "service.connected" in out
        assert needle in out
