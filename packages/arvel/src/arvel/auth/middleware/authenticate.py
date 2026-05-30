"""OptionalAuthenticate — resolves the current user without blocking unauthenticated requests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.auth.manager import AuthManager


class OptionalAuthenticate:
    """Resolves the current user and attaches to request.state.user.

    Non-blocking variant — unauthenticated requests proceed with user=None.
    For the blocking variant that returns 401, use arvel.http.middleware.Authenticate.
    """

    def __init__(self, *, manager: AuthManager) -> None:
        self._manager = manager

    async def handle(self, request: Any, call_next: Any) -> Any:
        user = await self._manager.user(request)
        if hasattr(request, "state"):
            request.state.user = user
        return await call_next(request)
