"""Admin users controller: listing, lifecycle, role and permission management."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import require_permission, require_role_level, role_level, users
from app.http.controllers._schemas import AssignRolePayload, GrantPermissionPayload
from app.models.user import User
from arvel.http.controller import Controller
from arvel.http.exceptions import AuthorizationException, NotFoundException
from arvel_permission.models import Permission, Role
from starlette.requests import Request
from starlette.responses import Response


class AdminUsersController(Controller):
    async def index(
        self,
        request: Request,
        trashed: str = "without",
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        await require_permission(request, "users.manage")
        return await users.list_users(trashed=trashed, search=search, limit=limit, offset=offset)

    async def show(self, user_id: int, request: Request) -> dict[str, Any]:
        await require_permission(request, "users.manage")
        user = await users.get_user(user_id)
        if user is None:
            raise NotFoundException("User not found.")
        return {"data": user}

    async def destroy(self, user_id: int, request: Request) -> Response:
        await require_permission(request, "users.manage")
        await users.soft_delete(user_id)
        return Response(status_code=204)

    async def force_destroy(self, user_id: int, request: Request) -> Response:
        await require_role_level(request, "users.manage", 100)
        await users.force_delete(user_id)
        return Response(status_code=204)

    async def suspend(self, user_id: int, request: Request) -> dict[str, Any]:
        actor = await require_permission(request, "users.manage")
        if int(actor.id) == user_id:
            raise AuthorizationException("Cannot suspend your own account.")
        result = await users.suspend(user_id)
        if result is None:
            raise NotFoundException("User not found.")
        return {"data": result}

    async def unsuspend(self, user_id: int, request: Request) -> dict[str, Any]:
        await require_permission(request, "users.manage")
        result = await users.unsuspend(user_id)
        if result is None:
            raise NotFoundException("User not found.")
        return {"data": result}

    async def restore(self, user_id: int, request: Request) -> dict[str, Any]:
        await require_permission(request, "users.manage")
        result = await users.restore(user_id)
        if result is None:
            raise NotFoundException("User not found.")
        return {"data": result}

    async def assign_role(
        self, user_id: int, payload: AssignRolePayload, request: Request
    ) -> dict[str, Any]:
        actor = await require_permission(request, "roles.manage")
        level = await role_level(payload.role)
        if not actor.has_level(level):
            raise AuthorizationException("Cannot assign a role above your level.")
        target: User | None = (
            await User.with_("roles", "permissions").where(User.id == user_id).first()
        )
        role_obj: Role | None = await Role.where(name=payload.role, guard_name="api").first()
        if target is None:
            raise NotFoundException("User not found.")
        if role_obj is None:
            raise NotFoundException(f"Role '{payload.role}' not found.")
        target.assign_role(role_obj)
        await target.save()
        return {"data": await users.get_user(user_id)}

    async def revoke_role(self, user_id: int, role_name: str, request: Request) -> dict[str, Any]:
        await require_permission(request, "roles.manage")
        target: User | None = await User.with_("roles").where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        target.remove_role(role_name)
        await target.save()
        return {"data": await users.get_user(user_id)}

    async def grant_permission(
        self, user_id: int, payload: GrantPermissionPayload, request: Request
    ) -> dict[str, Any]:
        await require_permission(request, "roles.manage")
        perm_obj: Permission | None = await Permission.where(name=payload.permission).first()
        if perm_obj is None:
            raise NotFoundException(f"Permission '{payload.permission}' not found.")
        target: User | None = (
            await User.with_("roles", "permissions").where(User.id == user_id).first()
        )
        if target is None:
            raise NotFoundException("User not found.")
        target.give_permission_to(perm_obj)
        await target.save()
        return {"data": await users.get_user(user_id)}

    async def revoke_permission(
        self, user_id: int, permission_name: str, request: Request
    ) -> dict[str, Any]:
        await require_permission(request, "roles.manage")
        perm_obj: Permission | None = await Permission.where(name=permission_name).first()
        if perm_obj is None:
            raise NotFoundException(f"Permission '{permission_name}' not found.")
        target: User | None = (
            await User.with_("roles", "permissions").where(User.id == user_id).first()
        )
        if target is None:
            raise NotFoundException("User not found.")
        target.revoke_permission_to(perm_obj)
        await target.save()
        return {"data": await users.get_user(user_id)}
