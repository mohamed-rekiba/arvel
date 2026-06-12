"""LogManager — Laravel-parity channel-based log manager."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from arvel.logging.channels.base import LogChannel


def _build_otel(name: str, _cfg: dict[str, Any]) -> LogChannel:
    from arvel.logging.channels.otel_channel import OtelChannel

    return OtelChannel(name)


def _build_single(_name: str, cfg: dict[str, Any]) -> LogChannel:
    from arvel.logging.channels.file_channel import SingleFileChannel

    return SingleFileChannel(
        path=str(cfg.get("path", "storage/logs/app.log")),
        level=str(cfg.get("level", "info")),
    )


def _build_daily(_name: str, cfg: dict[str, Any]) -> LogChannel:
    from arvel.logging.channels.file_channel import DailyFileChannel

    return DailyFileChannel(
        path=str(cfg.get("path", "storage/logs/app.log")),
        days=int(cfg.get("days", 7)),
        level=str(cfg.get("level", "info")),
    )


def _build_stderr(_name: str, cfg: dict[str, Any]) -> LogChannel:
    from arvel.logging.channels.stderr_channel import StderrChannel

    return StderrChannel(level=str(cfg.get("level", "info")))


def _build_null(_name: str, _cfg: dict[str, Any]) -> LogChannel:
    from arvel.logging.channels.null_channel import NullChannel

    return NullChannel()


def _build_syslog(_name: str, cfg: dict[str, Any]) -> LogChannel:
    from arvel.logging.channels.syslog_channel import SyslogChannel

    return SyslogChannel(level=str(cfg.get("level", "info")))


# Registry maps driver name → (name, cfg) -> LogChannel.
# Stack is handled separately because it needs manager.
_DRIVER_BUILDERS: dict[str, Any] = {
    "otel": _build_otel,
    "single": _build_single,
    "daily": _build_daily,
    "stderr": _build_stderr,
    "null": _build_null,
    "syslog": _build_syslog,
}


class LogManager:
    """Reads ``config/logging.py`` and routes log calls to the right channel(s).

    The manager caches built channel instances.  ``with_context()`` returns a
    cloned manager that passes the bound fields to every delegation call —
    it does NOT mutate the cached channels.
    """

    def __init__(
        self,
        default: str,
        channels: dict[str, dict[str, Any]],
        bound: dict[str, object] | None = None,
        shared_context: dict[str, object] | None = None,
        cache: dict[str, LogChannel] | None = None,
    ) -> None:
        self._default = default
        self._channels_cfg = channels
        self._bound: dict[str, object] = dict(bound or {})
        # Shared context is mutated by share_context() and is the same object
        # for all clones produced by with_context() — it propagates globally.
        self._shared: dict[str, object] = shared_context if shared_context is not None else {}
        # Channel instances are shared across clones (same drivers, no re-init).
        self._cache: dict[str, LogChannel] = cache if cache is not None else {}

    # ─────────────────────────── Channel resolution ───────────────────────────

    def channel(self, name: str | None = None) -> LogChannel:
        """Return the named (or default) channel, building and caching it first."""
        key = name or self._default
        if key not in self._cache:
            self._cache[key] = self._build(key)
        return self._cache[key]

    def stack(self, *channels: str, ignore_exceptions: bool = False) -> LogChannel:
        """Return an ad-hoc ``StackChannel`` wrapping the named channels."""
        from arvel.logging.channels.stack_channel import StackChannel

        return StackChannel(
            [self.channel(n) for n in channels],
            ignore_exceptions=ignore_exceptions,
        )

    def _build(self, name: str) -> LogChannel:
        """Construct the channel instance for ``name``.

        On any construction failure falls back to an ``OtelChannel("emergency")``
        so a bad channel config never silences the entire app.
        """
        try:
            return self._build_from_cfg(name)
        except (KeyError, ValueError, ImportError, AttributeError, OSError) as exc:
            from arvel.logging.channels.otel_channel import OtelChannel

            emergency = OtelChannel("emergency")
            emergency.error(
                "log.channel.build_failed",
                channel=name,
                error=str(exc),
            )
            return emergency

    def _build_from_cfg(self, name: str) -> LogChannel:
        cfg = self._channels_cfg.get(name)
        if cfg is None:
            raise KeyError(f"Log channel '{name}' is not defined in config/logging.py")

        driver: str = str(cfg.get("driver", name))

        if driver == "stack":
            return self._build_stack_channel(cfg)

        builder = _DRIVER_BUILDERS.get(driver)
        if builder is None:
            raise ValueError(f"Unknown log driver '{driver}' for channel '{name}'")
        return cast("LogChannel", builder(name, cfg))

    def _build_stack_channel(self, cfg: dict[str, Any]) -> LogChannel:
        from arvel.logging.channels.stack_channel import StackChannel

        sub_names: list[str] = list(cfg.get("channels", []))
        ignore = bool(cfg.get("ignore_exceptions", False))
        return StackChannel(
            [self._build(n) for n in sub_names],
            ignore_exceptions=ignore,
        )

    # ─────────────────────────── Context management ───────────────────────────

    def share_context(self, **fields: object) -> None:
        """Merge ``fields`` into the process-wide shared context (affects all clones)."""
        self._shared.update(fields)

    def flush_shared_context(self) -> None:
        """Clear the process-wide shared context."""
        self._shared.clear()

    def with_context(self, **fields: object) -> LogManager:
        """Return a cloned manager that injects ``fields`` into every log call."""
        return LogManager(
            default=self._default,
            channels=self._channels_cfg,
            bound={**self._bound, **fields},
            shared_context=self._shared,
            cache=self._cache,
        )

    # ─────────────────────────── Log delegation ───────────────────────────────

    def _merged(self, context: dict[str, object]) -> dict[str, object]:
        return {**self._shared, **self._bound, **context}

    def debug(self, message: str, **context: object) -> None:
        self.channel().debug(message, **self._merged(context))

    def info(self, message: str, **context: object) -> None:
        self.channel().info(message, **self._merged(context))

    def warning(self, message: str, **context: object) -> None:
        self.channel().warning(message, **self._merged(context))

    def error(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None:
        exc_info = context.pop("exc_info", False)
        if exc_info and exc is None:
            exc = sys.exc_info()[1]
        self.channel().error(message, exc=exc, **self._merged(context))

    def critical(self, message: str, **context: object) -> None:
        self.channel().critical(message, **self._merged(context))

    def exception(self, message: str, **context: object) -> None:
        self.channel().exception(message, **self._merged(context))


__all__ = ["LogManager"]
