"""Session facade — @classmethod API proxying to the bound SessionManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from arvel.container import Container
    from arvel.session import SessionManager


class Session:
    """Facade providing a classmethod API for the session subsystem.

    Bound by ``SessionServiceProvider.register()``.
    """

    _manager: ClassVar[SessionManager | None] = None

    @classmethod
    def bind(cls, container: Container) -> None:
        from arvel.session import SessionManager

        cls._manager = container.make(SessionManager)

    @classmethod
    def manager(cls) -> SessionManager:
        if cls._manager is None:
            from arvel.cache.exceptions import FacadeNotBoundError

            raise FacadeNotBoundError("Session")
        return cls._manager


__all__ = ["Session"]
