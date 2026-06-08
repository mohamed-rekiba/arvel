"""HasRoles and HasPermissions mixins — async-first authorization API.

The host model declares ``roles`` / ``permissions`` as
:class:`~arvel.database.orm.MorphToMany` accessors over the polymorphic
``model_has_roles`` / ``model_has_permissions`` pivots::

    class User(Model, HasRoles, HasPermissions):
        roles: ClassVar[MorphToMany[Role]] = MorphToMany(
            Role, table=model_has_roles, name="model", related_key="role_id"
        )
        permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
            Permission, table=model_has_permissions, name="model", related_key="permission_id"
        )

Every method runs against the active session: ``await user.assign_role("admin")``,
``await user.has_permission_to("posts.edit")``. The accessor writes the
``model_type`` discriminator on each INSERT, so polymorphic grants always
persist (no more silent ``model_type``-NULL). Permission lookups through roles
load ``role.permissions`` via the ``BelongsToMany`` accessor on demand.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self
from typing import cast as typing_cast

from arvel.database.orm.morph_map import get_morph_alias
from arvel.database.session import get_active_session
from sqlalchemy import Integer, Table, cast, select
from sqlalchemy.sql.elements import ColumnElement

from arvel_permission.models import (
    Permission,
    Role,
    model_has_permissions,
    model_has_roles,
)
from arvel_permission.service import GuardMismatchError

if TYPE_CHECKING:
    from arvel.database.orm import MorphToMany
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel_permission.config import PermissionConfig


class _ModelWithTable(Protocol):
    __table__: ClassVar[Table]


def _primary_key_column(model: type[object]) -> ColumnElement[Any]:
    return typing_cast("type[_ModelWithTable]", model).__table__.c["id"]


def _column(model: type[object], name: str) -> ColumnElement[Any]:
    # Clean models type class attributes as their Python type, not ColumnElement.
    # Go through the Core table to compare a column against a literal.
    return typing_cast("type[_ModelWithTable]", model).__table__.c[name]


def _enum_or_str(value: str) -> str:
    """Return value.value when it's a StrEnum, else the bare string."""
    if isinstance(value, enum.Enum):
        return str(value.value)
    return value


@dataclass(slots=True)
class _ModelTypes:
    role_model: type[Role]
    permission_model: type[Permission]


_MODEL_TYPES = _ModelTypes(role_model=Role, permission_model=Permission)


def _check_guard(item_guard: str, requested_guard: str | None) -> None:
    if requested_guard is None:
        return
    if item_guard != requested_guard:
        raise GuardMismatchError(
            f"Item belongs to guard '{item_guard}' but caller asked about '{requested_guard}'."
        )


def matches_wildcard(pattern: str, ability: str) -> bool:
    """Return True if ``pattern`` is a wildcard that covers ``ability``.

    Supported patterns (Apache Shiro wildcard model):
    - ``"*"`` — matches any ability string.
    - ``"resource.*"`` — matches any ``resource.{action}``.
    - ``"posts,users.create,update"`` — comma-separated OR within each segment.
    - ``"*.create,update"`` — star on one segment, OR list on another.
    """
    if pattern == "*":
        return True
    if "*" not in pattern and "," not in pattern:
        return False
    parts = pattern.split(".")
    ability_parts = ability.split(".")
    if len(parts) != len(ability_parts):
        return False
    for p, a in zip(parts, ability_parts, strict=True):
        allowed = {x.strip() for x in p.split(",")}
        if "*" not in allowed and a not in allowed:
            return False
    return True


def _perm_matches(held: Permission, target: Permission, *, wildcards: bool) -> bool:
    """True when ``held`` satisfies ``target`` (exact or wildcard)."""
    if held.name == target.name and held.guard_name == target.guard_name:
        return True
    return (
        wildcards
        and held.guard_name == target.guard_name
        and matches_wildcard(held.name, target.name)
    )


def apply_wildcard_config(config: PermissionConfig) -> None:
    """Apply ``config.wildcard_enabled`` as the class-level default for all models."""
    HasPermissions.wildcard_permission = config.wildcard_enabled


def apply_model_config(config: PermissionConfig) -> None:
    """Apply custom Role and Permission model classes to the mixins."""
    _MODEL_TYPES.role_model = config.role_model
    _MODEL_TYPES.permission_model = config.permission_model


def _get_events_config(instance: object) -> PermissionConfig | None:
    """Return the PermissionConfig attached to ``instance``, or None."""
    return getattr(instance, "_permission_config", None)


async def _resolve_role(value: Role | str, guard: str) -> Role:
    """Find-or-create the Role for ``value`` (dedups by name/guard)."""
    name = value.name if isinstance(value, Role) else _enum_or_str(value)
    item_guard = value.guard_name if isinstance(value, Role) else guard
    session = get_active_session()
    return await _MODEL_TYPES.role_model.find_or_create(name, session=session, guard=item_guard)


async def _resolve_permission(value: Permission | str, guard: str) -> Permission:
    """Find-or-create the Permission for ``value`` (dedups by name/guard)."""
    name = value.name if isinstance(value, Permission) else _enum_or_str(value)
    item_guard = value.guard_name if isinstance(value, Permission) else guard
    session = get_active_session()
    return await _MODEL_TYPES.permission_model.find_or_create(
        name, session=session, guard=item_guard
    )


class HasRoles:
    """Mixin that gives a model role management.

    The host must declare ``roles`` as a ``MorphToMany[Role]`` over the
    ``model_has_roles`` pivot.
    """

    default_guard_name: ClassVar[str] = "web"

    if TYPE_CHECKING:
        # Type hints only — the host supplies the real descriptor.
        roles: ClassVar[MorphToMany[Role]]
        id: int

    async def assign_role(self, *roles: Role | str) -> Self:
        guard = self.default_guard_name
        added: list[Role] = []
        for raw in roles:
            role = await _resolve_role(raw, guard)
            if await self.roles.attach(role.id):
                added.append(role)
        self._dispatch_role_events("attached", added)
        return self

    async def remove_role(self, *roles: Role | str) -> Self:
        guard = self.default_guard_name
        targets: set[tuple[str, str]] = set()
        for r in roles:
            if isinstance(r, Role):
                targets.add((r.name, r.guard_name))
            else:
                targets.add((_enum_or_str(r), guard))
        removed = [r for r in await self.roles.all() if (r.name, r.guard_name) in targets]
        for role in removed:
            await self.roles.detach(role.id)
        self._dispatch_role_events("detached", removed)
        return self

    async def sync_roles(self, roles: Sequence[Role | str], *, detach: bool = True) -> Self:
        guard = self.default_guard_name
        resolved = [await _resolve_role(r, guard) for r in roles]
        ids = [r.id for r in resolved]
        if detach:
            await self.roles.sync(ids)
        else:
            await self.roles.sync_without_detaching(ids)
        return self

    async def has_role(self, role: Role | str, *, guard: str | None = None) -> bool:
        if isinstance(role, Role):
            target_name, target_guard = role.name, role.guard_name
        else:
            target_guard = guard or self.default_guard_name
            target_name = _enum_or_str(role)
        _check_guard(target_guard, guard)
        return any(
            r.name == target_name and r.guard_name == target_guard for r in await self.roles.all()
        )

    async def has_any_role(self, *roles: Role | str) -> bool:
        for r in roles:
            if await self.has_role(r):
                return True
        return False

    async def has_all_roles(self, *roles: Role | str) -> bool:
        for r in roles:
            if not await self.has_role(r):
                return False
        return True

    async def get_role_names(self) -> list[str]:
        return [r.name for r in await self.roles.all()]

    async def has_level(self, minimum: int) -> bool:
        """Return True when the model's highest-level role meets or exceeds ``minimum``."""
        return max((r.level for r in await self.roles.all()), default=0) >= minimum

    def _dispatch_role_events(self, action: str, roles: list[Role]) -> None:
        """Fire role events if a PermissionConfig with events_enabled is attached."""
        if not roles:
            return
        config = _get_events_config(self)
        if config is None or not config.events_enabled:
            return
        try:
            from arvel_permission import events  # noqa: PLC0415

            event_cls = (
                events.RoleAttachedEvent if action == "attached" else events.RoleDetachedEvent
            )
            for role in roles:
                events.fire(event_cls(model=self, role=role))
        except ImportError:
            pass

    @classmethod
    async def query_with_role(
        cls,
        role: Role | str,
        *,
        session: AsyncSession,
        guard: str = "web",
    ) -> Sequence[Self]:
        """Return all instances of this model that hold the given role."""
        role_name = role.name if isinstance(role, Role) else role
        pk = _primary_key_column(cls)
        subq = (
            select(cast(model_has_roles.c.model_id, Integer))
            .join(Role, model_has_roles.c.role_id == Role.id)
            .where(
                _column(Role, "name") == role_name,
                _column(Role, "guard_name") == guard,
                model_has_roles.c.model_type == get_morph_alias(cls),
            )
        )
        result = await session.execute(select(cls).where(pk.in_(subq)))
        return result.scalars().all()

    @classmethod
    async def query_without_role(
        cls,
        role: Role | str,
        *,
        session: AsyncSession,
        guard: str = "web",
    ) -> Sequence[Self]:
        """Return all instances of this model that do NOT hold the given role."""
        role_name = role.name if isinstance(role, Role) else role
        pk = _primary_key_column(cls)
        subq = (
            select(cast(model_has_roles.c.model_id, Integer))
            .join(Role, model_has_roles.c.role_id == Role.id)
            .where(
                _column(Role, "name") == role_name,
                _column(Role, "guard_name") == guard,
                model_has_roles.c.model_type == get_morph_alias(cls),
            )
        )
        result = await session.execute(select(cls).where(~pk.in_(subq)))
        return result.scalars().all()


class HasPermissions:
    """Mixin that gives a model permission management.

    The host must declare ``permissions`` as a ``MorphToMany[Permission]`` over
    ``model_has_permissions``. If it also mixes in ``HasRoles``, permissions
    inherited via roles are merged in ``get_all_permissions``.
    """

    default_guard_name: ClassVar[str] = "web"
    wildcard_permission: bool = True

    if TYPE_CHECKING:
        permissions: ClassVar[MorphToMany[Permission]]
        # Present when the host also mixes in HasRoles; guarded at runtime.
        roles: ClassVar[MorphToMany[Role]]
        id: int

    async def give_permission_to(self, *perms: Permission | str) -> Self:
        guard = self.default_guard_name
        added: list[Permission] = []
        for raw in perms:
            perm = await _resolve_permission(raw, guard)
            if await self.permissions.attach(perm.id):
                added.append(perm)
        self._dispatch_permission_events("attached", added)
        return self

    async def revoke_permission_to(self, *perms: Permission | str) -> Self:
        guard = self.default_guard_name
        targets: set[tuple[str, str]] = set()
        for p in perms:
            if isinstance(p, Permission):
                targets.add((p.name, p.guard_name))
            else:
                targets.add((_enum_or_str(p), guard))
        removed = [p for p in await self.permissions.all() if (p.name, p.guard_name) in targets]
        for perm in removed:
            await self.permissions.detach(perm.id)
        self._dispatch_permission_events("detached", removed)
        return self

    async def sync_permissions(self, perms: Sequence[Permission | str]) -> Self:
        guard = self.default_guard_name
        resolved = [await _resolve_permission(p, guard) for p in perms]
        await self.permissions.sync([p.id for p in resolved])
        return self

    async def _roles_for_permission_check(self) -> list[Role]:
        """Roles attached to this host, or empty when it has no roles relation."""
        accessor = getattr(self, "roles", None)
        if accessor is None:
            return []
        return list(await accessor.all())

    async def has_permission_to(
        self, permission: Permission | str, *, guard: str | None = None
    ) -> bool:
        """Return True when the model holds the permission directly or via a role.

        Also matches wildcard patterns (``"*"``, ``"resource.*"``,
        ``"res1,res2.action1,action2"``) held by the model.
        """
        target = (
            permission
            if isinstance(permission, Permission)
            else _MODEL_TYPES.permission_model(
                name=_enum_or_str(permission),
                guard_name=guard or self.default_guard_name,
            )
        )
        _check_guard(target.guard_name, guard)
        wildcards = getattr(self, "wildcard_permission", True)

        if any(_perm_matches(p, target, wildcards=wildcards) for p in await self.permissions.all()):
            return True

        for role in await self._roles_for_permission_check():
            if any(
                _perm_matches(p, target, wildcards=wildcards) for p in await role.permissions.all()
            ):
                return True
        return False

    async def has_any_permission(self, *perms: Permission | str) -> bool:
        for p in perms:
            if await self.has_permission_to(p):
                return True
        return False

    async def has_all_permissions(self, *perms: Permission | str) -> bool:
        for p in perms:
            if not await self.has_permission_to(p):
                return False
        return True

    async def get_all_permissions(self) -> list[Permission]:
        seen: set[tuple[str, str]] = set()
        out: list[Permission] = []
        for p in await self.permissions.all():
            key = (p.name, p.guard_name)
            if key not in seen:
                seen.add(key)
                out.append(p)
        for role in await self._roles_for_permission_check():
            for p in await role.permissions.all():
                key = (p.name, p.guard_name)
                if key not in seen:
                    seen.add(key)
                    out.append(p)
        return out

    async def get_permission_names(self) -> list[str]:
        return [p.name for p in await self.get_all_permissions()]

    async def get_direct_permissions(self) -> list[Permission]:
        """Return only permissions granted directly to this model (not via roles)."""
        return list(await self.permissions.all())

    async def get_permissions_via_roles(self) -> list[Permission]:
        """Return permissions inherited through roles (not directly granted)."""
        seen: set[tuple[str, str]] = set()
        out: list[Permission] = []
        for role in await self._roles_for_permission_check():
            for p in await role.permissions.all():
                key = (p.name, p.guard_name)
                if key not in seen:
                    seen.add(key)
                    out.append(p)
        return out

    def _dispatch_permission_events(self, action: str, perms: list[Permission]) -> None:
        """Fire permission events if a PermissionConfig with events_enabled is attached."""
        if not perms:
            return
        config = _get_events_config(self)
        if config is None or not config.events_enabled:
            return
        try:
            from arvel_permission import events  # noqa: PLC0415

            event_cls = (
                events.PermissionAttachedEvent
                if action == "attached"
                else events.PermissionDetachedEvent
            )
            for perm in perms:
                events.fire(event_cls(model=self, permission=perm))
        except ImportError:
            pass

    @classmethod
    async def query_with_permission(
        cls,
        permission: Permission | str,
        *,
        session: AsyncSession,
        guard: str = "web",
    ) -> Sequence[Self]:
        """Return all instances of this model that hold the given permission (direct)."""
        perm_name = permission.name if isinstance(permission, Permission) else permission
        pk = _primary_key_column(cls)
        subq = (
            select(cast(model_has_permissions.c.model_id, Integer))
            .join(Permission, model_has_permissions.c.permission_id == Permission.id)
            .where(
                _column(Permission, "name") == perm_name,
                _column(Permission, "guard_name") == guard,
                model_has_permissions.c.model_type == get_morph_alias(cls),
            )
        )
        result = await session.execute(select(cls).where(pk.in_(subq)))
        return result.scalars().all()

    @classmethod
    async def query_without_permission(
        cls,
        permission: Permission | str,
        *,
        session: AsyncSession,
        guard: str = "web",
    ) -> Sequence[Self]:
        """Return all instances of this model that do NOT hold the given permission."""
        perm_name = permission.name if isinstance(permission, Permission) else permission
        pk = _primary_key_column(cls)
        subq = (
            select(cast(model_has_permissions.c.model_id, Integer))
            .join(Permission, model_has_permissions.c.permission_id == Permission.id)
            .where(
                _column(Permission, "name") == perm_name,
                _column(Permission, "guard_name") == guard,
                model_has_permissions.c.model_type == get_morph_alias(cls),
            )
        )
        result = await session.execute(select(cls).where(~pk.in_(subq)))
        return result.scalars().all()


# Role manages its own permissions (Role.permissions is a BelongsToMany over
# role_has_permissions) and Permission manages its own roles. Grafted here
# (module end) to break the models ↔ traits import cycle.
_HP_METHODS = (
    "give_permission_to",
    "revoke_permission_to",
    "sync_permissions",
    "has_permission_to",
    "has_any_permission",
    "has_all_permissions",
    "get_all_permissions",
    "get_permission_names",
    "get_direct_permissions",
    "get_permissions_via_roles",
    "_roles_for_permission_check",
    "_dispatch_permission_events",
)
for _method_name in _HP_METHODS:
    setattr(Role, _method_name, HasPermissions.__dict__[_method_name])


_HR_METHODS = (
    "assign_role",
    "remove_role",
    "sync_roles",
    "has_role",
    "has_any_role",
    "has_all_roles",
    "get_role_names",
    "_dispatch_role_events",
)
for _method_name in _HR_METHODS:
    setattr(Permission, _method_name, HasRoles.__dict__[_method_name])
