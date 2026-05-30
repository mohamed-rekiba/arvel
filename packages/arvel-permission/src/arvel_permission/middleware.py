"""Route middleware for arvel-permission — Spatie parity for role/permission guards.

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


class RoleMiddleware:
    """Guard a route to users that hold the specified role.

    Accepts pipe-separated values: ``"admin|manager"`` passes if the user has
    either role.
    """

    def __init__(self, role: str, *, guard: str = "web") -> None:
        self._roles = _split(role)
        self._guard = guard

    async def __call__(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
    ) -> Any:
        user = getattr(request, "user", None)
        if user is None:
            raise UnauthorizedException(status_code=401)
        check = getattr(user, "has_role", None)
        if check is None or not any(check(r, guard=self._guard) for r in self._roles):
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

    async def __call__(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
    ) -> Any:
        user = getattr(request, "user", None)
        if user is None:
            raise UnauthorizedException(status_code=401)
        check = getattr(user, "has_permission_to", None)
        if check is None or not any(check(p, guard=self._guard) for p in self._permissions):
            raise UnauthorizedException(status_code=403)
        return await call_next(request)


class RoleOrPermissionMiddleware:
    """Guard a route to users that hold either the specified role or permission.

    Accepts pipe-separated values on both the role and permission sides.
    """

    def __init__(self, role_or_permission: str, *, guard: str = "web") -> None:
        self._values = _split(role_or_permission)
        self._guard = guard

    async def __call__(
        self,
        request: Any,
        call_next: Callable[..., Awaitable[Any]],
    ) -> Any:
        user = getattr(request, "user", None)
        if user is None:
            raise UnauthorizedException(status_code=401)
        has_role = getattr(user, "has_role", None)
        has_perm = getattr(user, "has_permission_to", None)
        if not any(
            (has_role and has_role(v, guard=self._guard))
            or (has_perm and has_perm(v, guard=self._guard))
            for v in self._values
        ):
            raise UnauthorizedException(status_code=403)
        return await call_next(request)
