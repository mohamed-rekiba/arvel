"""Log facade — ergonomic surface over OTel logging."""

from __future__ import annotations

from arvel.logging.otel_logger import OtelLogger

_default_logger: OtelLogger = OtelLogger("arvel")


class _LogFacade:
    """Class-level namespace that delegates to a shared OtelLogger.

    Usage::

        Log.info("user.created", user_id=42)
        child = Log.with_context(request_id="abc")
        child.warning("rate.limited")
        Log.channel("payments").error("charge.failed", amount=99)
    """

    def debug(self, message: str, **context: object) -> None:
        _default_logger.debug(message, **context)

    def info(self, message: str, **context: object) -> None:
        _default_logger.info(message, **context)

    def warning(self, message: str, **context: object) -> None:
        _default_logger.warning(message, **context)

    def error(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None:
        _default_logger.error(message, exc=exc, **context)

    def critical(self, message: str, **context: object) -> None:
        _default_logger.critical(message, **context)

    def with_context(self, **fields: object) -> OtelLogger:
        """Return a child logger with additional bound fields."""
        return _default_logger.with_context(**fields)

    def channel(self, name: str) -> OtelLogger:
        """Return a logger using `name` as the OTel instrumentation scope."""
        return _default_logger.channel(name)


Log: _LogFacade = _LogFacade()

__all__ = ["Log"]
