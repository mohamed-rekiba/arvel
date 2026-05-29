"""Application lifecycle error classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.providers import ServiceProvider


class BootError(RuntimeError):
    """Raised when a provider fails during register() or boot()."""

    def __init__(self, provider: type[ServiceProvider], original: BaseException) -> None:
        self.provider = provider
        self.original = original
        super().__init__(
            f"Provider {provider.__qualname__} failed during boot: {original!r}",
        )


class ShutdownError(RuntimeError):
    """Raised when a provider fails during shutdown()."""

    def __init__(self, provider: type[ServiceProvider], original: BaseException) -> None:
        self.provider = provider
        self.original = original
        super().__init__(
            f"Provider {provider.__qualname__} failed during shutdown: {original!r}",
        )


class EnvironmentNotSetError(RuntimeError):
    """Raised when accessing environment() before it's been configured."""
