"""Guard ABC and UserResolver Protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UserResolver(Protocol):
    """Lookup contract for guards."""

    async def by_id(self, user_id: str) -> Any | None: ...
    async def by_credentials(self, credentials: dict[str, object]) -> Any | None: ...


class Guard(ABC):
    """Resolves the current user from a request."""

    @abstractmethod
    async def user(self, request: Any) -> Any | None: ...

    async def login(self, _user: Any, _request: Any) -> None:
        """Override in stateful guards. Stateless guards (JWT, Token) ignore this."""
        return

    async def logout(self, _request: Any) -> None:
        """Override in stateful guards. Stateless guards ignore this."""
        return
