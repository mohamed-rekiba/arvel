"""Structured logging — a structlog-backed ``LogManager`` (``contracts.Logger``).

structlog is a light **core** dependency, so it is imported at module level; this
does not affect the startup NFR (``import arvel`` never imports ``arvel.kernel``).
``channel(name)`` selects a named sink; ``bind(**ctx)`` returns a context-bound
logger. Grounded in knowledge/port/04 (logging channels).
"""

from __future__ import annotations

from typing import Any

import structlog


class LogManager:
    """A structlog logger exposing the ``contracts.Logger`` surface."""

    def __init__(self, logger: Any = None) -> None:
        self._logger: Any = logger if logger is not None else structlog.get_logger()

    def channel(self, name: str) -> LogManager:
        # M6: bind on THIS logger so channel() keeps context already bound (e.g. via .bind());
        # the previous structlog.get_logger() started fresh and discarded it.
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
