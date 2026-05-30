"""Auth facade — static API over the bound AuthManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from arvel.auth.guard import Guard
    from arvel.auth.manager import AuthManager


class Auth:
    """Facade providing a classmethod API for authentication."""

    _manager: ClassVar[AuthManager | None] = None

    @classmethod
    def set_manager(cls, manager: AuthManager) -> None:
        cls._manager = manager

    @classmethod
    def _mgr(cls) -> AuthManager:
        if cls._manager is None:
            msg = "Auth facade is not bound. Did AuthServiceProvider run?"
            raise RuntimeError(msg)
        return cls._manager

    @classmethod
    def guard(cls, name: str | None = None) -> Guard:
        return cls._mgr().guard(name)

    @classmethod
    async def user(cls, request: Any) -> Any | None:
        return await cls._mgr().user(request)

    @classmethod
    async def check(cls, request: Any) -> bool:
        return await cls._mgr().check(request)

    @classmethod
    async def id(cls, request: Any) -> Any | None:
        return await cls._mgr().id(request)

    @classmethod
    async def attempt(cls, credentials: dict[str, object], request: Any) -> bool:
        return await cls._mgr().attempt(credentials, request)

    @classmethod
    async def login(cls, user: Any, request: Any) -> None:
        await cls._mgr().login(user, request)

    @classmethod
    async def logout(cls, request: Any) -> None:
        await cls._mgr().logout(request)
