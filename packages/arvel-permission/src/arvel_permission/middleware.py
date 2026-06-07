"""Route middleware for arvel-permission — role and permission guards.

Register these via ``PermissionServiceProvider.boot()`` as named middleware:

    router.middleware("role", RoleMiddleware)
    router.middleware("permission", PermissionMiddleware)
    router.middleware("role_or_permission", RoleOrPermissionMiddleware)

Then protect routes::

    @app.get("/admin", middleware=["role:admin"])
    async def admin_panel(request): ...

Raises :exc:`~arvel_permission.exceptions.UnauthorizedException` on auth failure
(status_code 401 when no user, 403 when the user lacks access). The exception
propagates to the framework exception handler; if nothing handles it, the same
HTTP response as before is returned as a fallback.

Pipe-separated values enable OR semantics::

    @app.get("/dashboard", middleware=["role:admin|manager"])
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from arvel_permission.exceptions import UnauthorizedException


def _split(value: str) -> list[str]:
    """Split a pipe-separated value into stripped parts."""
    return [p.strip() for p in value.split("|")]


def _current_user(request: Any) -> Any | None:
    # Arvel attaches the authenticated user to request.state.user (see
    # OptionalAuthenticate / CanMiddleware) — not Starlette's request.user.
    return getattr(getattr(request, "state", None), "user", None)


async def _any(
    check: Callable[..., Awaitable[bool]],
    values: list[str],
    guard: str,
) -> bool:
    """True if the async ``check`` passes for any value (short-circuits)."""
    for value in values:
        if await check(value, guard=guard):
            return True
    return False


class RoleMiddleware:
    """Guard a route to users that hold the specified role.

    Accepts pipe-separated values: ``"admin|manager"`` passes if the user has
    either role.
    """

    def __init__(self, role: str, *, guard: str = "web") -> None:
        self._roles = _split(role)
        self._guard = guard

    async def handle(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
    ) -> Any:
        user = _current_user(request)
        if user is None:
            raise UnauthorizedException(status_code=401)
        check = getattr(user, "has_role", None)
        if check is None or not await _any(check, self._roles, self._guard):
            raise UnauthorizedException(status_code=403)
        return await call_next(request)


class PermissionMiddleware:
    """Guard a route to users that hold the specified permission.

    Accepts pipe-separated values: ``"publish|edit"`` passes if the user has
    either permission.
    """

    def __init__(self, permission: str, *, guard: str = "web") -> None:
        self._permissions = _split(permission)
        self._guard = guard

    async def handle(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
    ) -> Any:
        user = _current_user(request)
        if user is None:
            raise UnauthorizedException(status_code=401)
        check = getattr(user, "has_permission_to", None)
        if check is None or not await _any(check, self._permissions, self._guard):
            raise UnauthorizedException(status_code=403)
        return await call_next(request)


class RoleOrPermissionMiddleware:
    """Guard a route to users that hold either the specified role or permission.

    Accepts pipe-separated values on both the role and permission sides.
    """

    def __init__(self, role_or_permission: str, *, guard: str = "web") -> None:
        self._values = _split(role_or_permission)
        self._guard = guard

    async def handle(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
    ) -> Any:
        user = _current_user(request)
        if user is None:
            raise UnauthorizedException(status_code=401)
        has_role = getattr(user, "has_role", None)
        has_perm = getattr(user, "has_permission_to", None)
        allowed = False
        for v in self._values:
            if (has_role is not None and await has_role(v, guard=self._guard)) or (
                has_perm is not None and await has_perm(v, guard=self._guard)
            ):
                allowed = True
                break
        if not allowed:
            raise UnauthorizedException(status_code=403)
        return await call_next(request)
