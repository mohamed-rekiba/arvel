"""Cache subsystem exceptions."""

from __future__ import annotations


class CacheException(Exception):
    """Base cache exception."""


class TagsNotSupported(CacheException):
    """Raised when a cache store doesn't support tag operations."""

    def __init__(self, store_name: str = "") -> None:
        name = f" (store: {store_name})" if store_name else ""
        super().__init__(f"Tags are not supported by this cache store{name}")


class FacadeNotBoundError(CacheException):
    """Raised when a facade is used before its provider registers it."""

    def __init__(self, facade_name: str = "Cache") -> None:
        super().__init__(
            f"{facade_name} facade is not bound. "
            f"Register {facade_name}ServiceProvider in bootstrap/providers.py."
        )


class LockTimeoutError(CacheException):
    """Raised when a lock cannot be acquired within the timeout."""


__all__ = [
    "CacheException",
    "FacadeNotBoundError",
    "LockTimeoutError",
    "TagsNotSupported",
]
