"""Bearer-token auth guard helpers for Arvel applications.

Provides ``require_auth`` for direct use, and ``make_permission_guard`` /
``make_role_level_guard`` factories that capture the application's User model
so the full guards can be wired once in ``_deps.py``::

    from arvel.auth.guards import require_auth, make_permission_guard, make_role_level_guard
    from app.models.user import User

    require_permission  = make_permission_guard(User)
    require_role_level  = make_role_level_guard(User)

``arvel_permission`` is imported lazily inside each guard so that ``arvel`` core
does not gain a hard dependency on it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from arvel.auth import get_auth_service
from arvel.auth.exceptions import AccountSuspendedError, InvalidCredentialsError
from arvel.http.exceptions import AuthorizationException, UnauthenticatedException

if TYPE_CHECKING:
    from starlette.requests import Request

__all__ = [
    "make_permission_guard",
    "make_role_level_guard",
    "require_auth",
]


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    prefix, _, token = header.partition(" ")
    if prefix.lower() != "bearer" or not token:
        return None
    return token.strip()


async def require_auth(request: Request) -> Any:
    """Resolve the bearer JWT and return the authenticated user object.

    Raises :class:`UnauthenticatedException` when the token is missing or invalid.
    Raises :class:`AuthorizationException` when the account is suspended.
    """
    token = _extract_bearer(request)
    if not token:
        raise UnauthenticatedException("Bearer token missing.")
    try:
        return await get_auth_service().me(access_token=token)
    except InvalidCredentialsError as exc:
        raise UnauthenticatedException("Invalid bearer token.") from exc
    except AccountSuspendedError as exc:
        raise AuthorizationException("Account suspended.") from exc


def make_permission_guard(user_model: type) -> Callable[..., Any]:
    """Return an async ``require_permission(request, perm)`` guard.

    ``user_model`` is the application's ORM User class (with arvel_permission
    traits). The guard loads the user with roles and permissions and checks
    ``has_permission_to(perm)``::

        require_permission = make_permission_guard(User)

        # In a controller:
        await require_permission(request, "products.create")

    Raises :class:`AuthorizationException` if the permission is not held.
    """

    async def require_permission(request: Request, perm: str) -> Any:
        raw_user = await require_auth(request)
        _model: Any = user_model
        user = await _model.where(_model.id == raw_user.id).first()
        if user is None or not await user.has_permission_to(perm):
            raise AuthorizationException(f"Permission '{perm}' required.")
        return user

    return require_permission


def make_role_level_guard(user_model: type) -> Callable[..., Any]:
    """Return an async ``require_role_level(request, perm, minimum)`` guard.

    Builds on top of ``make_permission_guard``::

        require_role_level = make_role_level_guard(User)

        # In a controller:
        await require_role_level(request, "admin.access", minimum=2)

    Raises :class:`AuthorizationException` if the level requirement is not met.
    """
    _require_permission = make_permission_guard(user_model)

    async def require_role_level(request: Request, perm: str, minimum: int) -> Any:
        user = await _require_permission(request, perm)
        if not await user.has_level(minimum):
            raise AuthorizationException(f"Role level {minimum} required.")
        return user

    return require_role_level
