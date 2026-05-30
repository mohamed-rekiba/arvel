"""E-commerce User model."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as _datetime
from typing import ClassVar

from arvel.auth.mixins import Authenticatable, HasApiTokens
from arvel.database import Model, SoftDeletes, Timestamps, datetime, enum, id_, string
from arvel_permission.models import Permission, Role
from arvel_permission.traits import (
    HasPermissions,
    HasRoles,
    make_permissions_relationship,
    make_roles_relationship,
)


class User(
    Model,
    Timestamps,
    SoftDeletes,
    Authenticatable,
    HasApiTokens,
    HasRoles,
    HasPermissions,
):
    """Application user for the e-commerce demo."""

    __tablename__ = "users"

    _auth_password_field: ClassVar[str] = "password"  # noqa: S105
    default_guard_name: str = "api"

    id: int = id_()
    name: str = string(120)
    email: str = string(254, unique=True, index=True)
    email_verified_at: _datetime | None = datetime(nullable=True, default=None)
    password: str = string(255)
    locale: str = string(10, default="en")
    theme: str = enum(["light", "dark", "system"], name="users_theme", default="system")
    suspended_at: _datetime | None = datetime(nullable=True, default=None)
    remember_token: str | None = string(100, nullable=True, default=None)

    roles: list[Role] = make_roles_relationship(lambda: User, model_type="User")
    permissions: list[Permission] = make_permissions_relationship(lambda: User, model_type="User")

    @property
    def is_admin(self) -> bool:
        return self.has_any_role("admin", "super_admin")

    @property
    def is_suspended(self) -> bool:
        return self.suspended_at is not None

    async def suspend(self) -> None:
        self.suspended_at = _datetime.now(UTC)
        await self.save()

    async def unsuspend(self) -> None:
        self.suspended_at = None
        await self.save()


__all__ = ["User"]
