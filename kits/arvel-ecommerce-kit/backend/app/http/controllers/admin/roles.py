"""Admin roles and permissions listing."""

from __future__ import annotations

from app.http.controllers._deps import require_permission
from app.http.controllers._responses import PermissionsListOut, RolesListOut
from arvel.http import Request
from arvel.http.controller import Controller
from arvel_permission.models import Permission, Role


class AdminRolesController(Controller):
    async def index(self, request: Request) -> RolesListOut:
        await require_permission(request, "roles.manage")
        roles: list[Role] = await Role.order_by("name").all()
        # Small, fixed set of roles — the per-role permission load is fine here.
        return RolesListOut.model_validate(
            {
                "data": [
                    {
                        "id": role.id,
                        "name": role.name,
                        "guard_name": role.guard_name,
                        "level": role.level,
                        "permissions": [p.name for p in await role.permissions.all()],
                    }
                    for role in roles
                ]
            }
        )

    async def permissions_index(self, request: Request) -> PermissionsListOut:
        await require_permission(request, "roles.manage")
        perms: list[Permission] = await Permission.order_by("name").all()
        return PermissionsListOut.model_validate(
            {
                "data": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "guard_name": p.guard_name,
                    }
                    for p in perms
                ]
            }
        )
