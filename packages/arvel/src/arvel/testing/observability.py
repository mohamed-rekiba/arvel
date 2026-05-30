"""In-memory OTel signal capture for tests — replaces RecordingLogManager."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk.util.instrumentation import InstrumentationScope

if TYPE_CHECKING:
    from opentelemetry.sdk._logs._internal import ReadableLogRecord

_UNSET_SCOPE = InstrumentationScope("")


@dataclass
class CapturedLogRecord:
    """Flattened view of a ReadableLogRecord for easy test assertions."""

    body: str
    attributes: dict[str, Any]
    severity_number: SeverityNumber
    instrumentation_scope: InstrumentationScope


class FakeObservability:
    """Context manager that installs in-memory OTel providers for the duration of a test.

    Captures logs, spans, and metrics emitted while active. Restores original
    providers on exit so contexts can be nested or reused within the same process.
    """

    def __init__(self) -> None:
        self._log_exporter: Any = None
        self._span_exporter: Any = None
        self._metric_reader: Any = None
        self._original_tracer_provider: Any = None
        self._original_logger_provider: Any = None
        self._original_meter_provider: Any = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Self:
        import opentelemetry._logs._internal as _logs_internal
        import opentelemetry.metrics._internal as _metrics_internal
        import opentelemetry.trace as _trace_mod
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import (
            InMemoryLogRecordExporter,
            SimpleLogRecordProcessor,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        # OTel SDK has no public API for resetting global providers; direct module-variable
        # access is intentional here — pyright: ignore[reportPrivateUsage] on each line.
        self._original_tracer_provider = _trace_mod._TRACER_PROVIDER  # pyright: ignore[reportPrivateUsage]
        self._original_logger_provider = _logs_internal._LOGGER_PROVIDER  # pyright: ignore[reportPrivateUsage]
        self._original_meter_provider = _metrics_internal._METER_PROVIDER  # pyright: ignore[reportPrivateUsage]

        # Reset "set once" guards so we can swap providers multiple times in tests
        _trace_mod._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
        _logs_internal._LOGGER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
        _metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]

        self._log_exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call] # OTel SDK lacks py.typed
        log_provider = LoggerProvider()
        log_provider.add_log_record_processor(SimpleLogRecordProcessor(self._log_exporter))
        _logs_internal._LOGGER_PROVIDER = log_provider  # pyright: ignore[reportPrivateUsage]

        self._span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(self._span_exporter))
        _trace_mod._TRACER_PROVIDER = tracer_provider  # pyright: ignore[reportPrivateUsage]

        self._metric_reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[self._metric_reader])
        _metrics_internal._METER_PROVIDER = meter_provider  # pyright: ignore[reportPrivateUsage]

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        import opentelemetry._logs._internal as _logs_internal
        import opentelemetry.metrics._internal as _metrics_internal
        import opentelemetry.trace as _trace_mod

        # Flush everything before restoring
        if self._log_exporter is not None:
            self._log_exporter.shutdown()
        if self._span_exporter is not None:
            self._span_exporter.shutdown()

        # Restore raw module variables and reset guards so the next context can swap again
        _trace_mod._TRACER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
        _logs_internal._LOGGER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]
        _metrics_internal._METER_PROVIDER_SET_ONCE._done = False  # pyright: ignore[reportPrivateUsage]

        _trace_mod._TRACER_PROVIDER = self._original_tracer_provider  # pyright: ignore[reportPrivateUsage]
        _logs_internal._LOGGER_PROVIDER = self._original_logger_provider  # pyright: ignore[reportPrivateUsage]
        _metrics_internal._METER_PROVIDER = self._original_meter_provider  # pyright: ignore[reportPrivateUsage]

    # ------------------------------------------------------------------
    # Captured signal accessors
    # ------------------------------------------------------------------

    @property
    def log_records(self) -> list[CapturedLogRecord]:
        if self._log_exporter is None:
            return []
        raw: tuple[ReadableLogRecord, ...] = self._log_exporter.get_finished_logs()
        return [
            CapturedLogRecord(
                body=str(r.log_record.body or ""),
                attributes=dict(r.log_record.attributes or {}),
                severity_number=r.log_record.severity_number or SeverityNumber.UNSPECIFIED,
                instrumentation_scope=r.instrumentation_scope or _UNSET_SCOPE,
            )
            for r in raw
        ]

    @property
    def spans(self) -> list[Any]:
        if self._span_exporter is None:
            return []
        return list(self._span_exporter.get_finished_spans())

    @property
    def metrics(self) -> list[Any]:
        """Return all collected metric data points from the in-memory reader."""
        if self._metric_reader is None:
            return []
        result: list[Any] = []
        metrics_data = self._metric_reader.get_metrics_data()
        if metrics_data is None:
            return result
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                result.extend(scope_metric.metrics)
        return result

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    def assert_logged(self, event: str, **attrs: object) -> None:
        """Assert that at least one log record with the given body and attributes was emitted."""
        records = self.log_records
        for r in records:
            if r.body != event:
                continue
            if all(r.attributes.get(k) == v for k, v in attrs.items()):
                return
        attr_str = ", ".join(f"{k}={v!r}" for k, v in attrs.items())
        raise AssertionError(
            f"No log record found with body={event!r}"
            + (f" and {attr_str}" if attr_str else "")
            + f"\nCaptured records: {[r.body for r in records]}"
        )

    def assert_span(self, name: str) -> None:
        """Assert that at least one span with the given name was recorded."""
        spans = self.spans
        if any(s.name == name for s in spans):
            return
        raise AssertionError(
            f"No span found with name={name!r}\nCaptured spans: {[s.name for s in spans]}"
        )

    def assert_no_error_logs(self) -> None:
        """Assert that no ERROR or higher records were emitted."""
        error_records = [
            r for r in self.log_records if r.severity_number.value >= SeverityNumber.ERROR.value
        ]
        if error_records:
            raise AssertionError(
                f"Expected no error logs but found: {[r.body for r in error_records]}"
            )


__all__ = ["CapturedLogRecord", "FakeObservability"]
