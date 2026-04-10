"""Auth guard middleware — multi-guard authentication for ASGI requests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from arvel.auth.auth_manager import AuthManager


class AuthGuardMiddleware:
    """ASGI middleware that authenticates requests via pluggable guards.

    Requires ``auth_manager`` and uses optional ``guard_name`` to select a guard.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_manager: AuthManager,
        guard_name: str | None = None,
        exclude_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self._auth_manager = auth_manager
        self._guard_name = guard_name
        self._exclude_paths = exclude_paths or set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exclude_paths:
            await self.app(scope, receive, send)
            return

        await self._authenticate_with_guard(scope, receive, send)

    async def _authenticate_with_guard(self, scope: Scope, receive: Receive, send: Send) -> None:
        guard = self._auth_manager.guard(self._guard_name)
        auth_context = await guard.authenticate(scope)

        if auth_context is None:
            response = guard.error_response()
            await response(scope, receive, send)
            return

        state: dict[str, Any] = scope.setdefault("state", {})
        state["auth_user_id"] = auth_context.sub
        state["auth_guard"] = auth_context.guard
        state["auth_roles"] = auth_context.roles
        state["auth_groups"] = auth_context.groups
        state["auth_context"] = auth_context

        await self.app(scope, receive, send)
