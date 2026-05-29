"""Admin roles and permissions listing."""

from __future__ import annotations

from typing import Any

from app.http.controllers._deps import require_permission
from arvel.http.controller import Controller
from arvel_permission.models import Permission, Role
from starlette.requests import Request


class AdminRolesController(Controller):
    async def index(self, request: Request) -> dict[str, Any]:
        await require_permission(request, "roles.manage")
        roles: list[Role] = await Role.order_by("name").all()
        return {
            "data": [
                {
                    "id": role.id,
                    "name": role.name,
                    "guard_name": role.guard_name,
                    "level": role.level,
                }
                for role in roles
            ]
        }

    async def permissions_index(self, request: Request) -> dict[str, Any]:
        await require_permission(request, "roles.manage")
        perms: list[Permission] = await Permission.order_by("name").all()
        return {
            "data": [
                {
                    "id": p.id,
                    "name": p.name,
                    "guard_name": p.guard_name,
                }
                for p in perms
            ]
        }
