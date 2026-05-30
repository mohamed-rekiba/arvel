"""AuthManager — routes requests to named guards."""

from __future__ import annotations

from typing import Any

from arvel.auth.exceptions import AuthConfigError
from arvel.auth.guard import Guard


class AuthManager:
    def __init__(self, *, guards: dict[str, Guard], default: str) -> None:
        self._guards = guards
        self._default = default

    def guard(self, name: str | None = None) -> Guard:
        key = name or self._default
        g = self._guards.get(key)
        if g is None:
            msg = f"Auth guard '{key}' is not configured."
            raise AuthConfigError(msg)
        return g

    async def user(self, request: Any) -> Any | None:
        return await self.guard().user(request)

    async def check(self, request: Any) -> bool:
        return await self.user(request) is not None

    async def id(self, request: Any) -> Any | None:
        user = await self.user(request)
        if user is None:
            return None
        return str(getattr(user, "id", None))

    async def attempt(self, credentials: dict[str, object], request: Any) -> bool:
        g = self.guard()
        if hasattr(g, "attempt"):
            return await g.attempt(credentials, request)  # type: ignore[no-any-return]
        return False

    async def login(self, user: Any, request: Any) -> None:
        await self.guard().login(user, request)

    async def logout(self, request: Any) -> None:
        await self.guard().logout(request)
