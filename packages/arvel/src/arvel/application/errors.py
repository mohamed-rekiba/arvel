"""Application lifecycle error classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.providers import ServiceProvider


class BootError(RuntimeError):
    """Raised when a provider or service fails during the boot lifecycle.

    ``provider`` is the failing provider class, or ``None`` for failures not tied
    to a provider (see :class:`ServiceConnectError`). Always present so callers
    can read it off any caught ``BootError`` without an attribute check.
    """

    provider: type[ServiceProvider] | None

    def __init__(
        self,
        provider: type[ServiceProvider],
        original: BaseException,
        *,
        phase: str = "boot",
    ) -> None:
        self.provider = provider
        self.original = original
        self.phase = phase
        super().__init__(
            f"Provider {provider.__qualname__} failed during {phase}: {original!r}",
        )


class ServiceConnectError(BootError):
    """Raised when a registered ``BaseService.connect()`` fails during boot.

    Subclasses ``BootError`` so callers can catch either with one ``except``;
    ``provider`` is ``None`` since the failure is a service, not a provider.
    """

    def __init__(self, service_name: str, original: BaseException) -> None:
        self.service_name = service_name
        self.original = original
        self.phase = "boot"
        self.provider = None
        RuntimeError.__init__(
            self,
            f"Service {service_name!r} failed to connect during boot: {original!r}",
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
