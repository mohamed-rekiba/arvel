"""E-commerce auth controller — extends the framework's AuthController.

login, register, refresh, logout, forgot-password, and reset-password are
inherited verbatim. Only ``me`` is overridden to add roles and permissions to
the /me response, since those require an eager DB load that the framework
AuthController cannot do generically.
"""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import require_auth
from app.models.user import User
from arvel.auth.http.controller import AuthController
from arvel.http.exceptions import UnauthenticatedException
from starlette.requests import Request


class EcommerceAuthController(AuthController):
    async def me(self, request: Request) -> dict[str, Any]:
        raw_user = await require_auth(request)
        user: User | None = await (
            User.with_("roles", "permissions").where(User.id == raw_user.id).first()
        )
        if user is None:
            raise UnauthenticatedException("User not found.")
        role_names: list[str] = []
        all_permissions: list[str] = []
        if hasattr(user, "roles") and user.roles:
            for role in user.roles:
                if role.name:
                    role_names.append(role.name)
                if hasattr(role, "permissions") and role.permissions:
                    all_permissions.extend(p.name for p in role.permissions if p.name)
        if hasattr(user, "permissions") and user.permissions:
            all_permissions.extend(p.name for p in user.permissions if p.name)
        return {
            "id": int(user.id),
            "name": str(user.name),
            "email": str(user.email),
            "locale": str(getattr(user, "locale", "en") or "en"),
            "theme": str(getattr(user, "theme", "system") or "system"),
            "roles": sorted(set(role_names)),
            "permissions": sorted(set(all_permissions)),
        }
