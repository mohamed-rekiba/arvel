"""Lock exceptions."""

from __future__ import annotations


class LockError(Exception):
    """Base exception for lock operations."""


class LockAcquisitionError(LockError):
    """Raised when a lock cannot be acquired.

    Attributes:
        key: The lock key that could not be acquired.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Failed to acquire lock on '{key}'")


class LockOwnershipError(LockError):
    """Raised when a release is attempted by a non-owner.

    Attributes:
        key: The lock key.
        expected_owner: The owner that holds the lock.
        actual_owner: The owner that attempted the release.
    """

    def __init__(self, key: str, expected_owner: str, actual_owner: str) -> None:
        self.key = key
        self.expected_owner = expected_owner
        self.actual_owner = actual_owner
        super().__init__(
            f"Cannot release lock '{key}': "
            f"held by '{expected_owner}', release attempted by '{actual_owner}'"
        )
