"""UserService — admin user management and suspension.

Role / permission assignment is handled directly in routes/api.py via
arvel-permission traits (HasRoles, HasPermissions) after WI-arvel-037.
"""

from __future__ import annotations

from typing import Any

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

        qb = User.with_("roles", "permissions")
        if trashed == "without":
            qb = qb.where_null(User.deleted_at)
        elif trashed == "only":
            qb = User.only_trashed()
        else:
            qb = qb.with_trashed()
        if search:
            qb = qb.where_any(["name", "email"], "ilike", f"%{search}%")

        users: list[User] = await qb.order_by("-created_at").limit(limit).offset(offset).all()
        return {"data": [self._format_user(u) for u in users], "total": total}

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = (
            await User.with_("roles", "permissions")
            .with_trashed()
            .where(User.id == user_id)
            .first()
        )
        if user is None:
            return None
        return self._format_user(user)

    async def suspend(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.find(user_id)
        if user is None:
            return None
        await user.suspend()
        return self._format_user(user)

    async def unsuspend(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.find(user_id)
        if user is None:
            return None
        await user.unsuspend()
        return self._format_user(user)

    async def soft_delete(self, user_id: int) -> None:
        user: User | None = await User.find(user_id)
        if user is not None:
            await user.delete()

    async def force_delete(self, user_id: int) -> None:
        user: User | None = await User.with_trashed().where(User.id == user_id).first()
        if user is not None:
            await user.force_delete()

    async def restore(self, user_id: int) -> dict[str, Any] | None:
        user: User | None = await User.with_trashed().where(User.id == user_id).first()
        if user is None:
            return None
        await user.restore()
        return self._format_user(user)

    @staticmethod
    def _format_user(user: User) -> dict[str, Any]:
        roles = [role.name or "" for role in (user.roles or [])]
        permissions = [perm.name or "" for perm in (user.permissions or [])]
        return {
            "id": int(user.id),
            "name": user.name or "",
            "email": user.email or "",
            "roles": sorted(set(roles)),
            "permissions": sorted(set(permissions)),
            "suspended_at": user.suspended_at.isoformat() if user.suspended_at else None,
            "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        }


__all__ = ["UserNotFoundError", "UserService"]
