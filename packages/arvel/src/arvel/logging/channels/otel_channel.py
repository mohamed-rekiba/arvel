"""OtelChannel — LogChannel wrapper around OtelLogger."""

from __future__ import annotations

from arvel.logging.otel_logger import OtelLogger


class OtelChannel:
    """Delegates to an ``OtelLogger`` so the LogManager can use OTel as a driver.

    The ``OtelLogger`` is created eagerly but the OTel SDK resolves the global
    ``LoggerProvider`` on every ``emit()`` call, so SDK initialization can
    happen after channel construction.
    """

    def __init__(
        self,
        name: str = "arvel",
        bound: dict[str, object] | None = None,
    ) -> None:
        self._name = name
        self._bound: dict[str, object] = dict(bound or {})
        self._otel = OtelLogger(name, bound=self._bound)

    def debug(self, message: str, **context: object) -> None:
        self._otel.debug(message, **context)

    def info(self, message: str, **context: object) -> None:
        self._otel.info(message, **context)

    def warning(self, message: str, **context: object) -> None:
        self._otel.warning(message, **context)

    def error(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None:
        self._otel.error(message, exc=exc, **context)

    def critical(self, message: str, **context: object) -> None:
        self._otel.critical(message, **context)

    def exception(self, message: str, **context: object) -> None:
        self._otel.exception(message, **context)

    def with_context(self, **fields: object) -> OtelChannel:
        return OtelChannel(self._name, bound={**self._bound, **fields})


__all__ = ["OtelChannel"]
