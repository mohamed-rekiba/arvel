"""OTel-backed logger — emits to the currently-installed LoggerProvider."""

from __future__ import annotations

import os
import sys
import traceback
from typing import Any, Self

from opentelemetry import trace as otel_trace
from opentelemetry._logs import LogRecord as OtelLogRecord
from opentelemetry._logs import SeverityNumber, get_logger_provider

_SEVERITY_MAP: dict[str, SeverityNumber] = {
    "debug": SeverityNumber.DEBUG,
    "info": SeverityNumber.INFO,
    "warning": SeverityNumber.WARN,
    "error": SeverityNumber.ERROR,
    "critical": SeverityNumber.FATAL,
}

_LEVEL_ORDER: dict[str, int] = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "warn": 2,
    "error": 3,
    "critical": 4,
}

_DEFAULT_REDACT_FIELDS = frozenset(
    {
        "password",
        "token",
        "secret",
        "authorization",
        "api_key",
        "private_key",
    }
)


def _get_redact_set() -> frozenset[str]:
    """Read redact list from env on every call so test monkeypatching works."""
    raw = os.environ.get("LOG_REDACT_FIELDS", "")
    if not raw:
        return _DEFAULT_REDACT_FIELDS
    return frozenset(f.strip().lower() for f in raw.split(",") if f.strip())


def _redact(attrs: dict[str, Any]) -> dict[str, Any]:
    redact_set = _get_redact_set()
    return {k: "[REDACTED]" if k.lower() in redact_set else v for k, v in attrs.items()}


def _inject_request_context(attrs: dict[str, Any]) -> None:
    from arvel.observability.context import get_request_context

    req_ctx = get_request_context()
    if req_ctx.request_id:
        attrs.setdefault("request_id", req_ctx.request_id)
    if req_ctx.user_id:
        attrs.setdefault("user_id", req_ctx.user_id)
    if req_ctx.route:
        attrs.setdefault("route", req_ctx.route)
    if req_ctx.service:
        attrs.setdefault("service", req_ctx.service)


# Keys the framework binds onto every log line when present in the active Context.
# Anything else in Context stays out of logs unless the caller passes it explicitly.
_BOUND_CONTEXT_KEYS = ("request_id", "user_id", "tenant_id")


def _inject_app_context(attrs: dict[str, Any]) -> None:
    from arvel.context import Context

    for key in _BOUND_CONTEXT_KEYS:
        value = Context.get(key)
        if value is not None:
            attrs.setdefault(key, value if isinstance(value, str) else str(value))


def _inject_trace_context(attrs: dict[str, Any]) -> None:
    span = otel_trace.get_current_span()
    span_ctx = span.get_span_context()
    if span_ctx.is_valid:
        attrs.setdefault("trace_id", format(span_ctx.trace_id, "032x"))
        attrs.setdefault("span_id", format(span_ctx.span_id, "016x"))


def _inject_exception(attrs: dict[str, Any], exc: BaseException) -> None:
    attrs["exception.type"] = type(exc).__qualname__
    attrs["exception.message"] = str(exc)
    attrs["exception.stacktrace"] = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )


class OtelLogger:
    """Thin wrapper over the OTel LoggerProvider — always uses the global provider.

    Picks it up fresh on every emit so FakeObservability context swaps work.
    """

    def __init__(
        self,
        name: str = "arvel",
        *,
        bound: dict[str, object] | None = None,
    ) -> None:
        self._name = name
        self._bound: dict[str, object] = dict(bound or {})

    def _emit(
        self,
        level: str,
        message: str,
        context: dict[str, object],
        exc: BaseException | None = None,
    ) -> None:
        # Level gating — reads LOG_LEVEL from env so monkeypatching in tests works
        configured_level = os.environ.get("LOG_LEVEL", "debug").lower()
        if _LEVEL_ORDER.get(level, 0) < _LEVEL_ORDER.get(configured_level, 1):
            return

        attrs: dict[str, Any] = {**self._bound, **context}
        attrs = _redact(attrs)
        _inject_request_context(attrs)
        _inject_app_context(attrs)
        _inject_trace_context(attrs)
        if exc is not None:
            _inject_exception(attrs, exc)

        severity = _SEVERITY_MAP.get(level, SeverityNumber.INFO)
        record = OtelLogRecord(
            body=message,
            severity_number=severity,
            severity_text=level.upper(),
            attributes=attrs,
        )
        # Always resolve the current provider so test swaps are transparent
        get_logger_provider().get_logger(self._name).emit(record)

    def debug(self, message: str, **context: object) -> None:
        self._emit("debug", message, context)

    def info(self, message: str, **context: object) -> None:
        self._emit("info", message, context)

    def warning(self, message: str, **context: object) -> None:
        self._emit("warning", message, context)

    def error(self, message: str, *, exc: BaseException | None = None, **context: object) -> None:
        # exc_info=True means "capture the currently active exception", same as stdlib logging
        if context.pop("exc_info", False) and exc is None:
            exc = sys.exc_info()[1]
        self._emit("error", message, context, exc=exc)

    def critical(self, message: str, **context: object) -> None:
        self._emit("critical", message, context)

    def exception(self, message: str, **context: object) -> None:
        """Log at ERROR level with the currently active exception attached (stdlib compatible)."""
        exc = sys.exc_info()[1]
        self._emit("error", message, context, exc=exc)

    def with_context(self, **fields: object) -> Self:
        return type(self)(self._name, bound={**self._bound, **fields})

    def channel(self, name: str) -> OtelLogger:
        """Return a logger scoped to the given channel name (OTel instrumentation scope).

        Prefixes with "arvel." when the name doesn't already start with it so all
        framework-emitted loggers share a consistent namespace.
        """
        scoped = name if name.startswith("arvel.") else f"arvel.{name}"
        return OtelLogger(scoped, bound=dict(self._bound))


__all__ = ["OtelLogger"]
