"""Log facade — ergonomic surface over LogManager (with OtelLogger fallback)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from arvel.logging.channels.base import LogChannel
    from arvel.logging.manager import LogManager


# Wrapping in a list avoids `global` (PLW0603) while keeping mutation clear.
_bound: list[Any] = []


def _default_logger() -> Any:
    """Return the bound LogManager, or a bare OtelLogger when unbound.

    The fallback keeps all existing tests and pre-boot log calls working
    without requiring the full provider stack to be up.
    """
    if _bound:
        return _bound[0]
    from arvel.logging.otel_logger import OtelLogger

    return OtelLogger("arvel")


class Log:
    """Static-method facade that delegates to the container-bound LogManager.

    Call ``Log.bind(manager)`` from ``LogServiceProvider.register()`` and
    ``Log.unbind()`` from ``LogServiceProvider.shutdown()``.

    All log methods also work before the provider is registered — they fall
    back to the bare ``OtelLogger``, so bootstrap log calls don't get swallowed.
    """

    @classmethod
    def bind(cls, manager: LogManager) -> None:
        _bound.clear()
        _bound.append(manager)

    @classmethod
    def unbind(cls) -> None:
        _bound.clear()

    @classmethod
    def channel(cls, name: str | None = None) -> LogChannel:
        """Return the named channel from the bound manager, or an OtelChannel.

        When unbound (pre-boot), the channel name is prefixed with "arvel."
        so the OTel instrumentation scope is "arvel.<name>" — matching the
        convention the framework uses for all its own loggers.
        """
        if _bound:
            return cast("LogChannel", _bound[0].channel(name))
        from arvel.logging.channels.otel_channel import OtelChannel

        channel_name = f"arvel.{name}" if name else "arvel"
        return OtelChannel(channel_name)

    @classmethod
    def stack(cls, *channels: str, ignore_exceptions: bool = False) -> LogChannel:
        if _bound:
            return cast(
                "LogChannel", _bound[0].stack(*channels, ignore_exceptions=ignore_exceptions)
            )
        from arvel.logging.channels.otel_channel import OtelChannel

        return OtelChannel("arvel")

    @classmethod
    def share_context(cls, **fields: object) -> None:
        if _bound:
            _bound[0].share_context(**fields)

    @classmethod
    def flush_shared_context(cls) -> None:
        if _bound:
            _bound[0].flush_shared_context()

    @classmethod
    def with_context(cls, **fields: object) -> Any:
        """Return a child manager/logger with additional bound fields."""
        return _default_logger().with_context(**fields)

    @classmethod
    def debug(cls, message: str, **context: object) -> None:
        _default_logger().debug(message, **context)

    @classmethod
    def info(cls, message: str, **context: object) -> None:
        _default_logger().info(message, **context)

    @classmethod
    def warning(cls, message: str, **context: object) -> None:
        _default_logger().warning(message, **context)

    @classmethod
    def error(
        cls,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None:
        _default_logger().error(message, exc=exc, **context)

    @classmethod
    def critical(cls, message: str, **context: object) -> None:
        _default_logger().critical(message, **context)

    @classmethod
    def exception(cls, message: str, **context: object) -> None:
        _default_logger().exception(message, **context)


__all__ = ["Log"]
