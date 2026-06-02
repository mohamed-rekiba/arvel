"""E-commerce User model."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as _datetime
from typing import TYPE_CHECKING, ClassVar

from arvel.auth.mixins import Authenticatable, HasApiTokens
from arvel.database import (
    Model,
    SoftDeletes,
    Timestamps,
    enum,
    id_,
    string,
)
from arvel.database.orm import MorphToMany
from arvel_permission.models import (
    Permission,
    Role,
    model_has_permissions,
    model_has_roles,
)
from arvel_permission.traits import HasPermissions, HasRoles

if TYPE_CHECKING:
    from arvel.database import HasMany, HasOne

    from app.models.cart import Cart
    from app.models.order import Order


class User(
    Model,
    Timestamps,
    SoftDeletes,
    Authenticatable,
    HasApiTokens,
    HasRoles,
    HasPermissions,
):
    """Application user for the e-commerce kit."""

    __tablename__ = "users"

    _auth_password_field: ClassVar[str] = "password"  # noqa: S105
    default_guard_name: ClassVar[str] = "api"

    id: int = id_()
    name: str = string(120)
    email: str = string(254, unique=True, index=True)
    email_verified_at: _datetime | None = None
    password: str
    locale: str = string(10, default="en")
    theme: str = enum(["light", "dark", "system"], name="users_theme", default="system")
    suspended_at: _datetime | None = None
    remember_token: str | None = string(100, nullable=True, default=None)

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )

    def orders(self) -> HasMany[Order]:
        return self.has_many("Order", foreign_key="user_id")

    def cart(self) -> HasOne[Cart]:
        return self.has_one("Cart", foreign_key="user_id")

    async def is_admin(self) -> bool:
        return await self.has_any_role("admin", "super_admin")

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
