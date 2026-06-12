"""StackChannel — fans out a single log call to multiple child channels."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.logging.channels.base import LogChannel


class StackChannel:
    """Broadcasts every log call to all channels in the stack.

    Mirrors Laravel's ``stack`` channel driver.  When ``ignore_exceptions``
    is ``False`` (default) the first channel failure aborts the fan-out.
    """

    def __init__(
        self,
        channels: list[LogChannel],
        *,
        ignore_exceptions: bool = False,
    ) -> None:
        self._channels = channels
        self._ignore_exceptions = ignore_exceptions

    def _fan_out(self, method: str, /, *args: object, **kwargs: object) -> None:
        for ch in self._channels:
            try:
                getattr(ch, method)(*args, **kwargs)
            except Exception:
                if not self._ignore_exceptions:
                    raise

    def debug(self, message: str, **context: object) -> None:
        self._fan_out("debug", message, **context)

    def info(self, message: str, **context: object) -> None:
        self._fan_out("info", message, **context)

    def warning(self, message: str, **context: object) -> None:
        self._fan_out("warning", message, **context)

    def error(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None:
        for ch in self._channels:
            try:
                ch.error(message, exc=exc, **context)
            except Exception:
                if not self._ignore_exceptions:
                    raise

    def critical(self, message: str, **context: object) -> None:
        self._fan_out("critical", message, **context)

    def exception(self, message: str, **context: object) -> None:
        self._fan_out("exception", message, **context)

    def with_context(self, **fields: object) -> StackChannel:
        return StackChannel(
            [ch.with_context(**fields) for ch in self._channels],
            ignore_exceptions=self._ignore_exceptions,
        )


__all__ = ["StackChannel"]
