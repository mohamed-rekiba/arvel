"""Storage exceptions."""

from __future__ import annotations


class StorageError(Exception):
    """Base exception for storage operations."""


class StoragePathError(StorageError):
    """Raised when a storage path fails sanitization.

    Attributes:
        path: The rejected path.
        reason: Why the path was rejected.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid storage path '{path}': {reason}")
