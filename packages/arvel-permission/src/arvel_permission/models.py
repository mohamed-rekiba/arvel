"""Role, Permission, and pivot tables for arvel-permission.

``Role`` and ``Permission`` enforce ``UNIQUE(name, guard_name)`` so the same
name can exist under multiple guards.

The three pivots are plain Core ``Table``s on ``Model.metadata`` with composite
primary keys (no surrogate id, no timestamps):

- ``model_has_roles`` / ``model_has_permissions`` are polymorphic. A host model
  links to them through a :class:`~arvel.database.orm.MorphToMany` accessor,
  which writes the ``model_type`` discriminator and string-casts the owner PK
  into the ``VARCHAR(36)`` ``model_id`` column on every INSERT. This is what
  killed the old ``model_type``-NULL bug class — the discriminator is no longer
  a constant-join column a ``secondary`` relationship could silently drop.
- ``role_has_permissions`` is a simple int↔int pivot exposed via
  :class:`~arvel.database.orm.BelongsToMany` on ``Role.permissions`` /
  ``Permission.roles``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from arvel.database.columns import field
from arvel.database.model import Model, Timestamps
from arvel.database.orm import BelongsToMany
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    select,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


model_has_permissions = Table(
    "model_has_permissions",
    Model.metadata,
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
    Column("model_type", String(255), primary_key=True),
    Column("model_id", String(36), primary_key=True),
    Column("guard_name", String(125), nullable=False, default="web"),
)

model_has_roles = Table(
    "model_has_roles",
    Model.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("model_type", String(255), primary_key=True),
    Column("model_id", String(36), primary_key=True),
    Column("guard_name", String(125), nullable=False, default="web"),
)

role_has_permissions = Table(
    "role_has_permissions",
    Model.metadata,
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class Role(Model, Timestamps):
    """A named role under a guard. Roles aggregate Permissions."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", "guard_name", name="roles_name_guard_unique"),)

    id: int = field(default=None, primary_key=True, init=False)
    name: str = field(length=125)
    guard_name: str = field(length=125, default="web")
    level: int = 0

    if TYPE_CHECKING:
        # Real descriptor assigned at module end (breaks the Role↔Permission cycle).
        # Kept out of runtime __annotations__ so SQLAlchemy doesn't try to map it.
        permissions: ClassVar[BelongsToMany[Permission]]

    @property
    def default_guard_name(self) -> str:
        return self.guard_name

    @classmethod
    async def find_by_name(cls, name: str, *, session: AsyncSession, guard: str = "web") -> Self:
        """Find a role by name/guard. Raises ``RoleDoesNotExist`` if absent."""
        from arvel_permission.exceptions import RoleDoesNotExist  # noqa: PLC0415

        stmt = select(cls).filter_by(name=name, guard_name=guard).limit(1)
        result = await session.execute(stmt)
        role = result.scalar_one_or_none()
        if role is None:
            raise RoleDoesNotExist(f"Role '{name}' does not exist under guard '{guard}'.")
        return role

    @classmethod
    async def find_by_id(cls, id_: int, *, session: AsyncSession) -> Self | None:
        return await session.get(cls, id_)

    @classmethod
    async def find_or_create(cls, name: str, *, session: AsyncSession, guard: str = "web") -> Self:
        """Return existing role by name/guard or create it."""
        stmt = select(cls).filter_by(name=name, guard_name=guard).limit(1)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        obj = cls(name=name, guard_name=guard)
        session.add(obj)
        await session.flush()
        return obj


class Permission(Model, Timestamps):
    """A named ability under a guard. Granted directly to models or via Roles."""

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("name", "guard_name", name="permissions_name_guard_unique"),)

    id: int = field(default=None, primary_key=True, init=False)
    name: str = field(length=125)
    guard_name: str = field(length=125, default="web")

    if TYPE_CHECKING:
        # Real descriptor assigned at module end (breaks the Role↔Permission cycle).
        roles: ClassVar[BelongsToMany[Role]]

    @property
    def default_guard_name(self) -> str:
        return self.guard_name

    @classmethod
    async def find_by_name(cls, name: str, *, session: AsyncSession, guard: str = "web") -> Self:
        """Find a permission by name/guard. Raises ``PermissionDoesNotExist`` if absent."""
        from arvel_permission.exceptions import PermissionDoesNotExist  # noqa: PLC0415

        stmt = select(cls).filter_by(name=name, guard_name=guard).limit(1)
        result = await session.execute(stmt)
        perm = result.scalar_one_or_none()
        if perm is None:
            raise PermissionDoesNotExist(
                f"Permission '{name}' does not exist under guard '{guard}'."
            )
        return perm

    @classmethod
    async def find_by_id(cls, id_: int, *, session: AsyncSession) -> Self | None:
        return await session.get(cls, id_)

    @classmethod
    async def find_or_create(cls, name: str, *, session: AsyncSession, guard: str = "web") -> Self:
        """Return existing permission by name/guard or create it."""
        stmt = select(cls).filter_by(name=name, guard_name=guard).limit(1)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        obj = cls(name=name, guard_name=guard)
        session.add(obj)
        await session.flush()
        return obj


Role.permissions = BelongsToMany(
    Permission,
    table=role_has_permissions,
    foreign_key="role_id",
    related_foreign_key="permission_id",
)
Permission.roles = BelongsToMany(
    Role,
    table=role_has_permissions,
    foreign_key="permission_id",
    related_foreign_key="role_id",
)
