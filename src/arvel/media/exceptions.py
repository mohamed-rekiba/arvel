"""Media library exceptions."""

from __future__ import annotations


class MediaError(Exception):
    """Base exception for media operations."""


class MediaValidationError(MediaError):
    """Raised when a file fails collection validation.

    Attributes:
        collection: The collection that rejected the file.
        reason: Why the file was rejected.
    """

    def __init__(self, collection: str, reason: str) -> None:
        self.collection = collection
        self.reason = reason
        super().__init__(f"Media validation failed for collection '{collection}': {reason}")


class MediaProcessingError(MediaError):
    """Raised when image processing (resize, compress) fails."""
