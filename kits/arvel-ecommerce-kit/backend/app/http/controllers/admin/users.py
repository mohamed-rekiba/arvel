"""Admin users controller: listing, lifecycle, role and permission management."""

from __future__ import annotations

from app.http.controllers._deps import (
    clamp_limit,
    clamp_offset,
    highest_role_level,
    require_permission,
    require_role_level,
    role_level,
    users,
)
from app.http.controllers._responses import AdminUserListOut, AdminUserWrapperOut
from app.http.controllers._schemas import AssignRolePayload, GrantPermissionPayload
from app.models.user import User
from arvel.http import Request
from arvel.http.controller import Controller
from arvel.http.exceptions import AuthorizationException, NotFoundException
from arvel_permission.models import Permission, Role
from starlette.responses import Response


async def _assert_outranks(actor: User, target: User) -> None:
    """Block lifecycle actions against a user who outranks the actor (OWASP A01).

    A peer rank is allowed (matches assign_role's >= convention). Acting on
    yourself always passes since your level equals your own.
    """
    if not await actor.has_level(await highest_role_level(target)):
        raise AuthorizationException("Cannot manage a user who outranks you.")


class AdminUsersController(Controller):
    async def index(
        self,
        request: Request,
        trashed: str = "without",
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminUserListOut:
        await require_permission(request, "users.manage")
        return AdminUserListOut.model_validate(
            await users.list_users(
                trashed=trashed,
                search=search,
                limit=clamp_limit(limit),
                offset=clamp_offset(offset),
            )
        )

    async def show(self, user_id: int, request: Request) -> AdminUserWrapperOut:
        await require_permission(request, "users.manage")
        user = await users.get_user(user_id)
        if user is None:
            raise NotFoundException("User not found.")
        return AdminUserWrapperOut.model_validate({"data": user})

    async def destroy(self, user_id: int, request: Request) -> Response:
        actor = await require_permission(request, "users.manage")
        if int(actor.id) == user_id:
            raise AuthorizationException("Cannot delete your own account.")
        target = await User.where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        await users.soft_delete(user_id)
        return Response(status_code=204)

    async def force_destroy(self, user_id: int, request: Request) -> Response:
        actor = await require_role_level(request, "users.manage", 100)
        if int(actor.id) == user_id:
            raise AuthorizationException("Cannot delete your own account.")
        target = await User.with_trashed().where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        await users.force_delete(user_id)
        return Response(status_code=204)

    async def suspend(self, user_id: int, request: Request) -> AdminUserWrapperOut:
        actor = await require_permission(request, "users.manage")
        if int(actor.id) == user_id:
            raise AuthorizationException("Cannot suspend your own account.")
        target = await User.where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        result = await users.suspend(user_id)
        if result is None:
            raise NotFoundException("User not found.")
        return AdminUserWrapperOut.model_validate({"data": result})

    async def unsuspend(self, user_id: int, request: Request) -> AdminUserWrapperOut:
        actor = await require_permission(request, "users.manage")
        target = await User.where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        result = await users.unsuspend(user_id)
        if result is None:
            raise NotFoundException("User not found.")
        return AdminUserWrapperOut.model_validate({"data": result})

    async def restore(self, user_id: int, request: Request) -> AdminUserWrapperOut:
        actor = await require_permission(request, "users.manage")
        target = await User.with_trashed().where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        result = await users.restore(user_id)
        if result is None:
            raise NotFoundException("User not found.")
        return AdminUserWrapperOut.model_validate({"data": result})

    async def assign_role(
        self, user_id: int, payload: AssignRolePayload, request: Request
    ) -> AdminUserWrapperOut:
        actor = await require_permission(request, "roles.manage")
        level = await role_level(payload.role)
        if not await actor.has_level(level):
            raise AuthorizationException("Cannot assign a role above your level.")
        target: User | None = await User.where(User.id == user_id).first()
        role_obj: Role | None = await Role.where(name=payload.role, guard_name="api").first()
        if target is None:
            raise NotFoundException("User not found.")
        if role_obj is None:
            raise NotFoundException(f"Role '{payload.role}' not found.")
        await _assert_outranks(actor, target)
        await target.assign_role(role_obj)
        return AdminUserWrapperOut.model_validate({"data": await users.get_user(user_id)})

    async def revoke_role(
        self, user_id: int, role_name: str, request: Request
    ) -> AdminUserWrapperOut:
        actor = await require_permission(request, "roles.manage")
        level = await role_level(role_name)
        if not await actor.has_level(level):
            raise AuthorizationException("Cannot revoke a role above your level.")
        target: User | None = await User.where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        await target.remove_role(role_name)
        return AdminUserWrapperOut.model_validate({"data": await users.get_user(user_id)})

    async def grant_permission(
        self, user_id: int, payload: GrantPermissionPayload, request: Request
    ) -> AdminUserWrapperOut:
        actor = await require_permission(request, "roles.manage")
        if not await actor.has_permission_to(payload.permission):
            raise AuthorizationException(
                f"Cannot grant a permission you do not hold: '{payload.permission}'."
            )
        perm_obj: Permission | None = await Permission.where(name=payload.permission).first()
        if perm_obj is None:
            raise NotFoundException(f"Permission '{payload.permission}' not found.")
        target: User | None = await User.where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        await target.give_permission_to(perm_obj)
        return AdminUserWrapperOut.model_validate({"data": await users.get_user(user_id)})

    async def revoke_permission(
        self, user_id: int, permission_name: str, request: Request
    ) -> AdminUserWrapperOut:
        actor = await require_permission(request, "roles.manage")
        if not await actor.has_permission_to(permission_name):
            raise AuthorizationException(
                f"Cannot revoke a permission you do not hold: '{permission_name}'."
            )
        perm_obj: Permission | None = await Permission.where(name=permission_name).first()
        if perm_obj is None:
            raise NotFoundException(f"Permission '{permission_name}' not found.")
        target: User | None = await User.where(User.id == user_id).first()
        if target is None:
            raise NotFoundException("User not found.")
        await _assert_outranks(actor, target)
        await target.revoke_permission_to(perm_obj)
        return AdminUserWrapperOut.model_validate({"data": await users.get_user(user_id)})
