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

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Literal

from arvel.auth import get_auth_service
from arvel.auth.exceptions import AccountSuspendedError, InvalidCredentialsError
from arvel.http.exceptions import AuthorizationException, UnauthenticatedException

if TYPE_CHECKING:
    from starlette.requests import Request

# A guard accepts either one permission or several. With several, ``match``
# picks the semantics: "all" (default) requires every permission, "any" one of.
PermissionSpec = str | Sequence[str]
MatchMode = Literal["all", "any"]

__all__ = [
    "make_permission_guard",
    "make_role_level_guard",
    "require_auth",
]


def _normalize_perms(spec: PermissionSpec) -> tuple[str, ...]:
    # str is itself a Sequence[str] — guard against iterating it into characters.
    return (spec,) if isinstance(spec, str) else tuple(spec)


def _perm_error(perms: tuple[str, ...], match: MatchMode) -> str:
    if len(perms) == 1:
        return f"Permission '{perms[0]}' required."
    joiner = " or " if match == "any" else " and "
    return f"Permission required: {joiner.join(perms)}."


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
    """Return an async ``require_permission(request, perm, *, match="all")`` guard.

    ``user_model`` is the application's ORM User class (with arvel_permission
    traits). ``perm`` is one permission or several; ``match`` picks "all" or
    "any" when several are given::

        require_permission = make_permission_guard(User)

        await require_permission(request, "products.create")
        await require_permission(request, ["products.view", "categories.view"])
        await require_permission(request, ["a", "b"], match="any")

    Raises :class:`AuthorizationException` if the requirement is not met.
    """

    async def require_permission(
        request: Request, perm: PermissionSpec, *, match: MatchMode = "all"
    ) -> Any:
        perms = _normalize_perms(perm)
        user = await require_auth(request)
        # me() already loads the configured user model; only reload when the auth
        # service is wired with a different model than this guard captured.
        if not isinstance(user, user_model):
            model: Any = user_model
            user = await model.where(model.id == user.id).first()
            if user is None:
                raise AuthorizationException(_perm_error(perms, match))
        granted = (
            await user.has_any_permission(*perms)
            if match == "any"
            else await user.has_all_permissions(*perms)
        )
        if not granted:
            raise AuthorizationException(_perm_error(perms, match))
        return user

    return require_permission


def make_role_level_guard(user_model: type) -> Callable[..., Any]:
    """Return an async ``require_role_level(request, perm, minimum, *, match="all")`` guard.

    Builds on top of ``make_permission_guard``::

        require_role_level = make_role_level_guard(User)

        await require_role_level(request, "admin.access", minimum=2)

    Raises :class:`AuthorizationException` if the level requirement is not met.
    """
    _require_permission = make_permission_guard(user_model)

    async def require_role_level(
        request: Request, perm: PermissionSpec, minimum: int, *, match: MatchMode = "all"
    ) -> Any:
        user = await _require_permission(request, perm, match=match)
        if not await user.has_level(minimum):
            raise AuthorizationException(f"Role level {minimum} required.")
        return user

    return require_role_level
