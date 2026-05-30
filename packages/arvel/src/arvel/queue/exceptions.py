"""Queue subsystem exceptions."""

from __future__ import annotations


class QueueException(Exception):
    """Base queue exception."""


class FacadeNotBoundError(QueueException):
    """Raised when the Bus facade is used before QueueServiceProvider registers it."""

    def __init__(self, facade_name: str = "Bus") -> None:
        super().__init__(
            f"{facade_name} facade is not bound. "
            f"Register QueueServiceProvider in bootstrap/providers.py."
        )


class UnknownDriverError(QueueException):
    """Raised when QueueManager is asked for an unregistered driver."""


class UnknownJobClassError(QueueException):
    """Raised when a job_class string is not in the allowlist registry."""


__all__ = [
    "FacadeNotBoundError",
    "QueueException",
    "UnknownDriverError",
    "UnknownJobClassError",
]
