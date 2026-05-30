"""Route uvicorn log records through the OTel pipeline instead of stdout."""

from __future__ import annotations

import logging


class _OtelBridgeHandler(logging.Handler):
    """Logging handler that emits to OTel LoggerProvider. Marked for identity checks."""

    _otel_bridge = True  # marker used by tests to detect our handler

    def __init__(self, logger_name: str) -> None:
        super().__init__()
        self._otel_logger_name = logger_name

    def emit(self, record: logging.LogRecord) -> None:
        from opentelemetry._logs import LogRecord as OtelLogRecord
        from opentelemetry._logs import SeverityNumber, get_logger_provider

        severity_map = {
            logging.DEBUG: SeverityNumber.DEBUG,
            logging.INFO: SeverityNumber.INFO,
            logging.WARNING: SeverityNumber.WARN,
            logging.ERROR: SeverityNumber.ERROR,
            logging.CRITICAL: SeverityNumber.FATAL,
        }
        severity = severity_map.get(record.levelno, SeverityNumber.INFO)

        otel_record = OtelLogRecord(
            body=self.format(record),
            severity_number=severity,
            severity_text=record.levelname,
            attributes={"logger.name": record.name},
        )
        get_logger_provider().get_logger(self._otel_logger_name).emit(otel_record)


def install_uvicorn_bridge() -> None:
    """Replace uvicorn's stdout handlers with OTel bridge handlers.

    Call once at application startup (ObservabilityServiceProvider.boot does this).
    Safe to call multiple times — subsequent calls are idempotent.
    """
    import os

    log_uvicorn_access = os.environ.get("LOG_UVICORN_ACCESS", "true").lower() != "false"

    for logger_name in ("uvicorn", "uvicorn.error"):
        _bridge_logger(logger_name)

    if log_uvicorn_access:
        _bridge_logger("uvicorn.access")
    else:
        # Silence entirely
        access_log = logging.getLogger("uvicorn.access")
        access_log.handlers = []
        access_log.propagate = False


def _bridge_logger(name: str) -> None:
    """Remove existing StreamHandlers and install an OTel bridge."""
    std_logger = logging.getLogger(name)
    # Remove handlers that aren't already our bridge
    std_logger.handlers = [h for h in std_logger.handlers if getattr(h, "_otel_bridge", False)]
    # Add bridge if not already present
    if not any(getattr(h, "_otel_bridge", False) for h in std_logger.handlers):
        std_logger.addHandler(_OtelBridgeHandler(name))
    std_logger.setLevel(logging.DEBUG)
    std_logger.propagate = False


__all__ = ["install_uvicorn_bridge"]
