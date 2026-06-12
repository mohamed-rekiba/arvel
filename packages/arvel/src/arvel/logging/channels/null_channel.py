"""NullChannel — discards every log record."""

from __future__ import annotations


class NullChannel:
    """Drops all log calls.  Mirrors Laravel's ``null`` channel driver."""

    def debug(self, message: str, **context: object) -> None:
        pass

    def info(self, message: str, **context: object) -> None:
        pass

    def warning(self, message: str, **context: object) -> None:
        pass

    def error(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None:
        pass

    def critical(self, message: str, **context: object) -> None:
        pass

    def exception(self, message: str, **context: object) -> None:
        pass

    def with_context(self, **_fields: object) -> NullChannel:
        return self


__all__ = ["NullChannel"]
