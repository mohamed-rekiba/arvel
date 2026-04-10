"""Queue-specific exceptions."""

from __future__ import annotations


class QueueError(Exception):
    """Base exception for the queue package."""


class JobTimeoutError(QueueError):
    """Job execution exceeded its timeout."""

    def __init__(self, message: str, *, job_class: str, timeout: int) -> None:
        super().__init__(message)
        self.job_class = job_class
        self.timeout = timeout


class JobMaxRetriesError(QueueError):
    """Job exhausted all retry attempts."""

    def __init__(self, message: str, *, job_class: str, attempts: int) -> None:
        super().__init__(message)
        self.job_class = job_class
        self.attempts = attempts


class QueueConnectionError(QueueError):
    """Cannot connect to the queue backend (e.g., Redis unreachable)."""

    def __init__(self, message: str, *, driver: str) -> None:
        super().__init__(message)
        self.driver = driver
