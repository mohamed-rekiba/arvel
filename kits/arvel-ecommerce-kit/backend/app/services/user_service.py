"""UserService — admin user management and suspension.

Role / permission assignment is handled in routes/api.py via
arvel-permission traits (HasRoles, HasPermissions).
"""

from __future__ import annotations

from typing import Any

from arvel.logging.facade import Log

from app.models.user import User


class UserNotFoundError(Exception):
    pass


class UserService:
    async def list_users(
        self,
        *,
        trashed: str = "without",
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        # Build a count query without eager-loading to avoid inflated counts from joins.
        count_qb = User.query()
        if trashed == "without":
            count_qb = count_qb.where_null(User.deleted_at)
        elif trashed == "only":
            count_qb = User.only_trashed()
        else:
            count_qb = count_qb.with_trashed()
        if search:
            count_qb = count_qb.where_any(["name", "email"], "ilike", f"%{search}%")
        total: int = await count_qb.count()

        qb = User.query()
        if trashed == "without":
            qb = qb.where_null(User.deleted_at)
        elif trashed == "only":
            qb = User.only_trashed()
        else:
            qb = qb.with_trashed()
        if search:
            qb = qb.where_any(["name", "email"], "ilike", f"%{search}%")

        # Eager-load roles + direct permissions in two batched queries (one per
        # relation) instead of two per user — kills the admin list N+1.
        users: list[User] = (
            await qb.with_("roles", "permissions")
            .order_by("-created_at")
            .limit(limit)
            .offset(offset)
            .all()
        )
        return {"data": [await self._format_user(u) for u in users], "total": total}

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.with_trashed().where(User.id == user_id).first()
        if user is None:
            return None
        return await self._format_user(user, effective=True)

    async def suspend(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.find(user_id)
        if user is None:
            return None
        Log.debug("user.suspending", user_id=user_id)
        await user.suspend()
        Log.debug("user.suspended", user_id=user_id)
        return await self._format_user(user, effective=True)

    async def unsuspend(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.find(user_id)
        if user is None:
            return None
        Log.debug("user.unsuspending", user_id=user_id)
        await user.unsuspend()
        Log.debug("user.unsuspended", user_id=user_id)
        return await self._format_user(user, effective=True)

    async def soft_delete(self, user_id: int) -> None:
        user: User | None = await User.find(user_id)
        if user is not None:
            Log.debug("user.deleting", user_id=user_id)
            await user.delete()
            Log.debug("user.deleted", user_id=user_id)

    async def force_delete(self, user_id: int) -> None:
        user: User | None = await User.with_trashed().where(User.id == user_id).first()
        if user is not None:
            Log.debug("user.force_deleting", user_id=user_id)
            await user.force_delete()
            Log.debug("user.force_deleted", user_id=user_id)

    async def restore(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.with_trashed().where(User.id == user_id).first()
        if user is None:
            return None
        Log.debug("user.restoring", user_id=user_id)
        await user.restore()
        Log.debug("user.restored", user_id=user_id)
        return await self._format_user(user, effective=True)

    @staticmethod
    async def _format_user(user: User, *, effective: bool = False) -> dict[str, Any]:
        roles = sorted({role.name or "" for role in await user.roles.all()})
        direct = await user.get_direct_permissions()
        direct_permissions = sorted({perm.name or "" for perm in direct})
        # The list view only needs direct grants (cheap, no per-user role expansion).
        # Detail views resolve the effective set so "Permissions" reflects what the
        # user can actually do — a super_admin with no direct grants isn't shown empty.
        if effective:
            permissions = sorted({p.name or "" for p in await user.get_all_permissions()})
        else:
            permissions = direct_permissions
        return {
            "id": int(user.id),
            "name": user.name or "",
            "email": user.email or "",
            "roles": roles,
            "permissions": permissions,
            "direct_permissions": direct_permissions,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "suspended_at": user.suspended_at.isoformat() if user.suspended_at else None,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        }


__all__ = ["UserNotFoundError", "UserService"]
