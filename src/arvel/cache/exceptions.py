"""Cache exceptions."""

from __future__ import annotations


class CacheError(Exception):
    """Base exception for cache operations."""


class CacheSerializationError(CacheError):
    """Raised when a cache value cannot be serialized to JSON.

    Attributes:
        key: The cache key that was being written.
        value_type: The type name of the value that failed serialization.
    """

    def __init__(self, key: str, value_type: str, detail: str = "") -> None:
        self.key = key
        self.value_type = value_type
        msg = f"Cannot serialize value of type '{value_type}' for cache key '{key}'"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
