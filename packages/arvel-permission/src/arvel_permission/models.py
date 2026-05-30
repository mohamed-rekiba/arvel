"""Role, Permission, and pivot ORM models for arvel-permission.

``Role`` and ``Permission`` enforce ``UNIQUE(name, guard_name)`` so the same
name can exist under multiple guards. ``ModelHasRole``, ``ModelHasPermission``,
and ``RoleHasPermission`` represent the polymorphic pivot tables.

Pivots use composite primary keys, matching Spatie's default migration schema
and providing DB-level duplicate prevention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from arvel.database.columns import id_, integer, string
from arvel.database.model import Model, Timestamps
from sqlalchemy import Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _StringId(TypeDecorator[str]):
    """VARCHAR column that coerces integer PKs to str at bind time.

    Asyncpg is strict about parameter types; passing an int for a VARCHAR
    parameter raises DataError. This decorator converts transparently.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return value


class Role(Model, Timestamps):
    """A named role under a guard. Roles aggregate Permissions."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", "guard_name", name="roles_name_guard_unique"),)

    id: Mapped[int] = id_(init=False)
    name: Mapped[str] = string(125)
    guard_name: Mapped[str] = string(125, default="web")
    level: Mapped[int] = integer(default=0)

    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary="role_has_permissions",
        primaryjoin="Role.id == foreign(RoleHasPermission.role_id)",
        secondaryjoin="foreign(RoleHasPermission.permission_id) == Permission.id",
        viewonly=False,
        lazy="selectin",
        default_factory=list,
        init=False,
        back_populates="roles",
    )

    @property
    def default_guard_name(self) -> str:
        return self.guard_name

    @classmethod
    async def find_by_name(cls, name: str, *, session: AsyncSession, guard: str = "web") -> Self:
        """Find a role by name/guard. Raises ``RoleDoesNotExist`` if absent."""
        from arvel_permission.exceptions import RoleDoesNotExist  # noqa: PLC0415

        stmt = select(cls).where(cls.name == name, cls.guard_name == guard).limit(1)
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
        stmt = select(cls).where(cls.name == name, cls.guard_name == guard).limit(1)
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

    id: Mapped[int] = id_(init=False)
    name: Mapped[str] = string(125)
    guard_name: Mapped[str] = string(125, default="web")

    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary="role_has_permissions",
        primaryjoin="Permission.id == foreign(RoleHasPermission.permission_id)",
        secondaryjoin="foreign(RoleHasPermission.role_id) == Role.id",
        viewonly=False,
        lazy="selectin",
        default_factory=list,
        init=False,
        back_populates="permissions",
    )

    @property
    def default_guard_name(self) -> str:
        return self.guard_name

    @classmethod
    async def find_by_name(cls, name: str, *, session: AsyncSession, guard: str = "web") -> Self:
        """Find a permission by name/guard. Raises ``PermissionDoesNotExist`` if absent."""
        from arvel_permission.exceptions import PermissionDoesNotExist  # noqa: PLC0415

        stmt = select(cls).where(cls.name == name, cls.guard_name == guard).limit(1)
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
        stmt = select(cls).where(cls.name == name, cls.guard_name == guard).limit(1)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        obj = cls(name=name, guard_name=guard)
        session.add(obj)
        await session.flush()
        return obj


class ModelHasRole(Model):
    """Polymorphic pivot — assigns a :class:`Role` to any model type.

    Composite PK ``(role_id, model_type, model_id)`` enforces uniqueness at the
    DB level: assigning the same role twice raises an IntegrityError.
    ``model_id`` is VARCHAR(36) to support both integer and UUID primary keys.
    """

    __tablename__ = "model_has_roles"
    __fillable__: ClassVar[list[str] | None] = ["role_id", "model_type", "model_id", "guard_name"]

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_type: Mapped[str] = mapped_column(String(255), primary_key=True)
    model_id: Mapped[str] = mapped_column(_StringId(36), primary_key=True)
    guard_name: Mapped[str] = string(125, default="web")


class ModelHasPermission(Model):
    """Polymorphic pivot — grants a :class:`Permission` directly to any model type.

    Composite PK ``(permission_id, model_type, model_id)`` enforces uniqueness.
    """

    __tablename__ = "model_has_permissions"
    __fillable__: ClassVar[list[str] | None] = [
        "permission_id",
        "model_type",
        "model_id",
        "guard_name",
    ]

    permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_type: Mapped[str] = mapped_column(String(255), primary_key=True)
    model_id: Mapped[str] = mapped_column(_StringId(36), primary_key=True)
    guard_name: Mapped[str] = string(125, default="web")


class RoleHasPermission(Model):
    """Pivot that grants a :class:`Permission` to a :class:`Role`.

    Composite PK ``(permission_id, role_id)`` matches the migration schema.
    """

    __tablename__ = "role_has_permissions"
    __fillable__: ClassVar[list[str] | None] = ["permission_id", "role_id"]

    permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
