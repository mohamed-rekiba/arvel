"""Public logging facade with Laravel-like ergonomics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from arvel.logging.channels import resolve_channel

if TYPE_CHECKING:
    from structlog.typing import FilteringBoundLogger


@dataclass(frozen=True, slots=True)
class LoggerFacade:
    """Thin wrapper over a structlog bound logger."""

    _logger: FilteringBoundLogger

    def named(self, name: str) -> LoggerFacade:
        """Return a logger bound to an explicit logger name."""
        return LoggerFacade(structlog.get_logger(name))

    def channel(self, name: str) -> LoggerFacade:
        """Return a logger bound to the named channel."""
        selected = resolve_channel(name)
        channel_logger = structlog.get_logger(f"arvel.logging.{selected.name}")
        return LoggerFacade(channel_logger.bind(channel=selected.name, driver=selected.driver))

    def with_context(self, **context: object) -> LoggerFacade:
        """Return a logger with additional structured context."""
        return LoggerFacade(self._logger.bind(**context))

    def debug(self, event: str, *args: object, **fields: object) -> None:
        self._logger.debug(event, *args, **fields)

    def info(self, event: str, *args: object, **fields: object) -> None:
        self._logger.info(event, *args, **fields)

    def warning(self, event: str, *args: object, **fields: object) -> None:
        self._logger.warning(event, *args, **fields)

    def error(self, event: str, *args: object, **fields: object) -> None:
        self._logger.error(event, *args, **fields)

    def critical(self, event: str, *args: object, **fields: object) -> None:
        self._logger.critical(event, *args, **fields)

    def exception(self, event: str, *args: object, **fields: object) -> None:
        self._logger.exception(event, *args, **fields)


def create_log_facade() -> LoggerFacade:
    """Create the root logger facade used by public API consumers."""
    return LoggerFacade(structlog.get_logger("arvel"))
