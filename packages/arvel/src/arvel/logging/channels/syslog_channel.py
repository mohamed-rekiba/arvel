"""SyslogChannel — writes to the local syslog daemon via SysLogHandler."""

from __future__ import annotations

import logging.handlers
import sys

from arvel.logging.channels.base import StdlibChannel


class SyslogChannel(StdlibChannel):
    """Mirrors Laravel's ``syslog`` channel driver.

    Writes to ``/dev/log`` on Linux or the UDP syslog port on macOS/Windows.
    Falls back to ``stderr`` when the local socket is unavailable.
    """

    def __init__(
        self,
        facility: int = logging.handlers.SysLogHandler.LOG_USER,
        level: str = "info",
        bound: dict[str, object] | None = None,
    ) -> None:
        try:
            if sys.platform == "darwin":
                handler: logging.Handler = logging.handlers.SysLogHandler(
                    address=("/var/run/syslog", logging.handlers.SYSLOG_UDP_PORT),
                    facility=facility,
                )
            else:
                handler = logging.handlers.SysLogHandler(
                    address="/dev/log",
                    facility=facility,
                )
        except OSError:
            import logging as _std

            handler = _std.StreamHandler()
        super().__init__(handler, name="syslog", level=level, bound=bound)


__all__ = ["SyslogChannel"]
