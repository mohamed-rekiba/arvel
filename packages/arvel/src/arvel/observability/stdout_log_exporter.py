"""Single-line stdout formatters for the no-collector case.

When no OTLP endpoint is set, signals still need to reach the operator's
terminal. OTel's console exporters dump a multi-line JSON blob per record/span
(the full resource included), which is unreadable in `docker compose logs`.
These formatters render one clean line instead: compact JSON for
`log_format=json`, human-readable for `log_format=console`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util import ns_to_iso_str
from opentelemetry.trace import format_span_id, format_trace_id

# Reserved top-level keys so user attributes can't shadow them in JSON output.
_RESERVED = ("timestamp", "level", "logger", "message", "trace_id", "span_id")


def _parts(record: ReadableLogRecord) -> tuple[str, str, str, str, dict[str, Any]]:
    lr = record.log_record
    ts_ns = lr.timestamp if lr.timestamp is not None else lr.observed_timestamp
    timestamp = ns_to_iso_str(ts_ns)
    level = lr.severity_text or "INFO"
    logger = record.instrumentation_scope.name if record.instrumentation_scope else "arvel"
    message = "" if lr.body is None else str(lr.body)
    attrs: dict[str, Any] = dict(lr.attributes) if lr.attributes else {}
    if lr.trace_id:
        attrs.setdefault("trace_id", format_trace_id(lr.trace_id))
    if lr.span_id:
        attrs.setdefault("span_id", format_span_id(lr.span_id))
    return timestamp, level, logger, message, attrs


def format_json(record: ReadableLogRecord) -> str:
    timestamp, level, logger, message, attrs = _parts(record)
    payload: dict[str, Any] = {
        "timestamp": timestamp,
        "level": level,
        "logger": logger,
        "message": message,
    }
    payload.update(
        {k: v for k, v in attrs.items() if k not in _RESERVED or k in ("trace_id", "span_id")}
    )
    return json.dumps(payload, default=str, separators=(",", ":")) + "\n"


def format_console(record: ReadableLogRecord) -> str:
    timestamp, level, logger, message, attrs = _parts(record)
    suffix = ""
    if attrs:
        suffix = "  " + " ".join(f"{k}={v}" for k, v in attrs.items())
    return f"{timestamp} {level:<8} {logger}  {message}{suffix}\n"


def formatter_for(log_format: str) -> Callable[[ReadableLogRecord], str]:
    """Pick the line formatter for the configured LOG_FORMAT."""
    return format_console if log_format == "console" else format_json


def format_span_console(span: ReadableSpan) -> str:
    """One readable line per span — beats OTel's multi-line JSON dump on stdout."""
    ctx = span.get_span_context()
    start = ns_to_iso_str(span.start_time) if span.start_time is not None else ""
    duration_ms = (
        (span.end_time - span.start_time) / 1_000_000
        if span.start_time is not None and span.end_time is not None
        else 0.0
    )
    trace_id = format_trace_id(ctx.trace_id) if ctx is not None else ""
    span_id = format_span_id(ctx.span_id) if ctx is not None else ""
    attrs = dict(span.attributes) if span.attributes else {}
    suffix = "  " + " ".join(f"{k}={v}" for k, v in attrs.items()) if attrs else ""
    return (
        f"{start} TRACE    {span.name}  "
        f"dur={duration_ms:.2f}ms trace_id={trace_id} span_id={span_id}"
        f"{suffix}\n"
    )


__all__ = ["format_console", "format_json", "format_span_console", "formatter_for"]
