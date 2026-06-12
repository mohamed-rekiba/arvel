"""LogChannel protocol and StdlibChannel base for stdlib-backed channel drivers."""

from __future__ import annotations

import logging
import sys
import traceback as _tb
from typing import Protocol

_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_LEVEL_ORDER: dict[str, int] = {
    "debug": 0,
    "info": 1,
    "warning": 2,
    "warn": 2,
    "error": 3,
    "critical": 4,
}

_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


class LogChannel(Protocol):
    """Common interface every channel driver must satisfy."""

    def debug(self, message: str, **context: object) -> None: ...

    def info(self, message: str, **context: object) -> None: ...

    def warning(self, message: str, **context: object) -> None: ...

    def error(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        **context: object,
    ) -> None: ...

    def critical(self, message: str, **context: object) -> None: ...

    def exception(self, message: str, **context: object) -> None: ...

    def with_context(self, **fields: object) -> LogChannel: ...


class StdlibChannel:
    """Base for all stdlib-backed channel drivers.

    Subclasses create the handler in ``_make_handler()`` and this base wires
    level-gating, context formatting, and ``with_context`` cloning.
    """

    def __init__(
        self,
        handler: logging.Handler,
        name: str = "arvel",
        level: str = "info",
        bound: dict[str, object] | None = None,
    ) -> None:
        self._handler = handler
        self._name = name
        self._level = level.lower()
        self._bound: dict[str, object] = dict(bound or {})

        # Private stdlib logger per (class, name) pair so handlers don't bleed
        # across instances. Propagation is disabled — we own the handler here.
        self._logger = logging.getLogger(f"arvel.channel.{name}.{id(self)}")
        self._logger.propagate = False
        self._logger.setLevel(logging.DEBUG)
        handler.setFormatter(_FORMATTER)
        if not self._logger.handlers:
            self._logger.addHandler(handler)

    def _passes_level(self, level: str) -> bool:
        return _LEVEL_ORDER.get(level, 0) >= _LEVEL_ORDER.get(self._level, 1)

    def _emit(
        self,
        level: str,
        message: str,
        context: dict[str, object],
        exc: BaseException | None = None,
    ) -> None:
        if not self._passes_level(level):
            return
        stdlib_level = _LEVEL_MAP.get(level, logging.INFO)
        extra_parts: list[str] = []
        merged = {**self._bound, **context}
        if merged:
            extra_parts.append(" ".join(f"{k}={v!r}" for k, v in merged.items()))
        text = message + (" | " + " ".join(extra_parts) if extra_parts else "")
        if exc is not None:
            tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
            text = f"{text}\n{tb}"
        self._logger.log(stdlib_level, text)

    def debug(self, message: str, **context: object) -> None:
        self._emit("debug", message, context)

    def info(self, message: str, **context: object) -> None:
        self._emit("info", message, context)

    def warning(self, message: str, **context: object) -> None:
        self._emit("warning", message, context)

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
        self._emit("error", message, context, exc=exc)

    def critical(self, message: str, **context: object) -> None:
        self._emit("critical", message, context)

    def exception(self, message: str, **context: object) -> None:
        exc = sys.exc_info()[1]
        self._emit("error", message, context, exc=exc)

    def replace_bound(self, bound: dict[str, object]) -> None:
        """Replace bound context fields — used by with_context() on clones."""
        self._bound = bound

    def with_context(self, **fields: object) -> StdlibChannel:
        import copy

        clone = copy.copy(self)
        clone.replace_bound({**self._bound, **fields})
        return clone


__all__ = ["LogChannel", "StdlibChannel"]
