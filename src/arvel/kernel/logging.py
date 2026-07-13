"""Structured logging — a structlog-backed ``LogManager`` (``contracts.Logger``).

structlog is a light **core** dependency, so it is imported at module level; this
does not affect the startup NFR (``import arvel`` never imports ``arvel.kernel``).
``channel(name)`` selects a named sink; ``bind(**ctx)`` returns a context-bound
logger. Grounded in knowledge/port/04 (logging channels).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

# configure_logging() rebuilds the processor list and would drop externally-inserted processors
# (e.g. telemetry's OTel bridge); the kernel can't import arvel.telemetry directly, so capabilities
# register a callback here instead and the kernel fires it after every (re)configuration.
_post_configure_hooks: list[Callable[[], None]] = []


def on_logging_configured(hook: Callable[[], None]) -> None:
    """Register a callback fired after each ``configure_logging`` run. Idempotent
    on identity — registering the same callable twice is a no-op."""
    if hook not in _post_configure_hooks:
        _post_configure_hooks.append(hook)


class LogManager:
    """A structlog logger exposing the ``contracts.Logger`` surface."""

    def __init__(self, logger: Any = None) -> None:
        self._logger: Any = logger if logger is not None else structlog.get_logger()

    def channel(self, name: str) -> LogManager:
        # bind on THIS logger (not a fresh structlog.get_logger()) so already-bound context survives
        return LogManager(self._logger.bind(channel=name))

    def bind(self, **kw: Any) -> LogManager:
        return LogManager(self._logger.bind(**kw))

    @staticmethod
    def with_context(**kw: Any) -> None:
        """Bind values into the ambient context so **every** subsequent log event in
        this async context (e.g. a request) carries them (structlog contextvars)."""
        structlog.contextvars.bind_contextvars(**kw)

    @staticmethod
    def clear_context() -> None:
        """Clear the ambient log context (call at the end of a request)."""
        structlog.contextvars.clear_contextvars()

    def debug(self, event: str, **kw: Any) -> None:
        self._logger.debug(event, **kw)

    def info(self, event: str, **kw: Any) -> None:
        self._logger.info(event, **kw)

    def warning(self, event: str, **kw: Any) -> None:
        self._logger.warning(event, **kw)

    def error(self, event: str, **kw: Any) -> None:
        self._logger.error(event, **kw)

    def critical(self, event: str, **kw: Any) -> None:
        self._logger.critical(event, **kw)


def configure_logging(*, json_logs: bool = False) -> None:
    """Configure structlog rendering: pretty console (dev) or JSON (prod).

    In JSON mode an ``exc_info`` is rendered as a **structured** ``exception`` field (a list of frame
    dicts) so production tracebacks are machine-parseable by log aggregators — not a flat multi-line
    string. Frame **locals are excluded** (``show_locals=False``): they routinely hold request data,
    passwords, and tokens, which must never leak into logs (rule 20-security). The console renderer
    formats ``exc_info`` as a pretty traceback itself, so it needs no extra processor."""
    from structlog.tracebacks import ExceptionDictTransformer

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if json_logs:
        # exc_info → structured frames, with frame locals excluded (secret-safe)
        processors.append(
            structlog.processors.ExceptionRenderer(ExceptionDictTransformer(show_locals=False))
        )
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    structlog.configure(processors=processors)
    # e.g. telemetry re-asserts its OTel log bridge, which this rebuild would otherwise drop
    for hook in _post_configure_hooks:
        hook()
