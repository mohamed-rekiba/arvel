"""Observability exceptions."""

from __future__ import annotations


class HealthCheckTimeoutError(Exception):
    """Raised when a health check exceeds its configured timeout."""

    def __init__(self, check_name: str, timeout: float) -> None:
        self.check_name = check_name
        self.timeout = timeout
        super().__init__(f"Health check '{check_name}' timed out after {timeout}s")


class TracingConfigError(Exception):
    """Raised when OpenTelemetry configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
