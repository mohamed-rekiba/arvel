"""Storage subsystem exceptions."""

from __future__ import annotations


class StoragePathError(PermissionError):
    """Raised when a path traversal attack is detected."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Path traversal attempt blocked: {path!r}")
        self.path = path


class StorageDriverError(OSError):
    """Base for storage driver errors."""


class StorageFileNotFoundError(FileNotFoundError, StorageDriverError):
    """Raised when a requested file does not exist on any storage disk.

    Subclasses the builtin ``FileNotFoundError`` so ``except FileNotFoundError``
    still catches it — every driver raises this one type for a missing object,
    so disk-agnostic callers can catch a single exception.
    """

    def __init__(self, path: str) -> None:
        super().__init__(f"File not found in storage: {path!r}")
        self.path = path


FileNotFoundError = StorageFileNotFoundError  # noqa: A001 — intentional alias for the storage module


__all__ = [
    "FileNotFoundError",
    "StorageDriverError",
    "StorageFileNotFoundError",
    "StoragePathError",
]
