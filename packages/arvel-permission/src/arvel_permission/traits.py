"""HasRoles and HasPermissions mixins — Spatie-shaped API for any model.

These mixins operate on the model's ``roles`` and ``permissions`` attributes
(populated by SQLAlchemy relationships in the application's user model).

They are deliberately synchronous and side-effect-light: ``assign_role``
mutates the ``self.roles`` list. Persistence is the application's job
(``await user.save()`` after a series of role/permission changes).

Factory functions (:func:`make_roles_relationship` and
:func:`make_permissions_relationship`) produce the SQLAlchemy ``relationship``
descriptors for models with integer PKs without requiring the caller to write
``cast(..., Integer)`` or suppress ``type: ignore[attr-defined]`` (ADR-094).
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self
from typing import cast as typing_cast

from sqlalchemy import Integer, String, Table, and_, cast
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.orm import Mapped, foreign, relationship
from sqlalchemy.sql.elements import ColumnElement

from arvel_permission.models import ModelHasPermission, ModelHasRole, Permission, Role
from arvel_permission.service import GuardMismatchError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel_permission.config import PermissionConfig


class _ModelWithTable(Protocol):
    __table__: ClassVar[Table]


def _primary_key_column(model: type[object]) -> ColumnElement[Any]:
    return typing_cast("type[_ModelWithTable]", model).__table__.c["id"]


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


def _coerce_role(value: Role | str, *, guard: str) -> Role:
    if isinstance(value, Role):
        return value
    return _MODEL_TYPES.role_model(name=_enum_or_str(value), guard_name=guard)


def _coerce_permission(value: Permission | str, *, guard: str) -> Permission:
    if isinstance(value, Permission):
        return value
    return _MODEL_TYPES.permission_model(name=_enum_or_str(value), guard_name=guard)


def _check_guard(item_guard: str, requested_guard: str | None) -> None:
    if requested_guard is None:
        return
    if item_guard != requested_guard:
        raise GuardMismatchError(
            f"Item belongs to guard '{item_guard}' but caller asked about '{requested_guard}'."
        )


def matches_wildcard(pattern: str, ability: str) -> bool:
    """Return True if ``pattern`` is a wildcard that covers ``ability``.

    Supported patterns (Spatie / Apache Shiro model):
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
    """Apply ``config.wildcard_enabled`` as the class-level default for all models.

    Called by ``PermissionServiceProvider.boot()``.  Model-level overrides
    (``wildcard_permission = True/False`` on the host class) still take priority.
    """
    HasPermissions.wildcard_permission = config.wildcard_enabled


def apply_model_config(config: PermissionConfig) -> None:
    """Apply custom Role and Permission model classes to the synchronous mixins."""
    _MODEL_TYPES.role_model = config.role_model
    _MODEL_TYPES.permission_model = config.permission_model


def _get_events_config(instance: object) -> PermissionConfig | None:
    """Return the PermissionConfig attached to ``instance``, or None."""
    return getattr(instance, "_permission_config", None)


class HasRoles:
    """Mixin that gives a model Spatie-style role management.

    The host class must expose a mutable ``roles`` collection of ``Role``
    instances (typically via a SQLAlchemy `relationship(...)`).
    """

    default_guard_name: str = "web"

    if TYPE_CHECKING:
        # Type hints only — not scanned by SQLAlchemy's declarative mapper.
        # The actual relationship is provided by the model or make_roles_relationship().
        roles: Mapped[list[Role]]
        id: Mapped[int]

    def assign_role(self, *roles: Role | str) -> Self:
        guard = self.default_guard_name
        existing = {(r.name, r.guard_name) for r in self.roles}
        added: list[Role] = []
        for raw in roles:
            role = _coerce_role(raw, guard=guard)
            key = (role.name, role.guard_name)
            if key not in existing:
                self.roles.append(role)
                existing.add(key)
                added.append(role)
        self._dispatch_role_events("attached", added)
        return self

    def remove_role(self, *roles: Role | str) -> Self:
        guard = self.default_guard_name
        targets: set[tuple[str, str]] = set()
        for r in roles:
            coerced = _coerce_role(r, guard=guard)
            targets.add((coerced.name, coerced.guard_name))
        removed = [r for r in self.roles if (r.name, r.guard_name) in targets]
        self.roles = [r for r in self.roles if (r.name, r.guard_name) not in targets]
        self._dispatch_role_events("detached", removed)
        return self

    def sync_roles(self, roles: Sequence[Role | str], *, detach: bool = True) -> Self:
        guard = self.default_guard_name
        if detach:
            self.roles = [_coerce_role(r, guard=guard) for r in roles]
        else:
            existing = {(r.name, r.guard_name) for r in self.roles}
            for raw in roles:
                role = _coerce_role(raw, guard=guard)
                if (role.name, role.guard_name) not in existing:
                    self.roles.append(role)
                    existing.add((role.name, role.guard_name))
        return self

    def has_role(self, role: Role | str, *, guard: str | None = None) -> bool:
        if isinstance(role, Role):
            target = role
        else:
            target = _MODEL_TYPES.role_model(name=role, guard_name=guard or self.default_guard_name)
        _check_guard(target.guard_name, guard)
        return any(r.name == target.name and r.guard_name == target.guard_name for r in self.roles)

    def has_any_role(self, *roles: Role | str) -> bool:
        return any(self.has_role(r) for r in roles)

    def has_all_roles(self, *roles: Role | str) -> bool:
        return all(self.has_role(r) for r in roles)

    def get_role_names(self) -> list[str]:
        return [r.name for r in self.roles]

    def has_level(self, minimum: int) -> bool:
        """Return True when the model's highest-level role meets or exceeds ``minimum``.

        Operates on the already-loaded ``roles`` relationship — no DB round-trip.
        Requires ``Role.level`` to be set (default 0 means no hierarchy).
        """
        return max((r.level for r in self.roles), default=0) >= minimum

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
        from sqlalchemy import select  # noqa: PLC0415

        role_name = role.name if isinstance(role, Role) else role
        pk = _primary_key_column(cls)
        subq = (
            select(cast(ModelHasRole.model_id, Integer))
            .join(Role, Role.id == ModelHasRole.role_id)
            .where(
                Role.name == role_name,
                Role.guard_name == guard,
                ModelHasRole.model_type == cls.__name__,
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
        from sqlalchemy import select  # noqa: PLC0415

        role_name = role.name if isinstance(role, Role) else role
        pk = _primary_key_column(cls)
        subq = (
            select(cast(ModelHasRole.model_id, Integer))
            .join(Role, Role.id == ModelHasRole.role_id)
            .where(
                Role.name == role_name,
                Role.guard_name == guard,
                ModelHasRole.model_type == cls.__name__,
            )
        )
        result = await session.execute(select(cls).where(~pk.in_(subq)))
        return result.scalars().all()


class HasPermissions:
    """Mixin that gives a model Spatie-style permission management.

    The host class must expose a mutable ``permissions`` collection of
    ``Permission`` instances. If it also mixes in ``HasRoles``, permissions
    inherited via roles are merged in ``get_all_permissions``.
    """

    default_guard_name: str = "web"
    wildcard_permission: bool = True

    if TYPE_CHECKING:
        # Same pattern as HasRoles — not scanned by SQLAlchemy's mapper.
        permissions: Mapped[list[Permission]]
        id: Mapped[int]

    def give_permission_to(self, *perms: Permission | str) -> Self:
        guard = self.default_guard_name
        existing = {(p.name, p.guard_name) for p in self.permissions}
        added: list[Permission] = []
        for raw in perms:
            perm = _coerce_permission(raw, guard=guard)
            key = (perm.name, perm.guard_name)
            if key not in existing:
                self.permissions.append(perm)
                existing.add(key)
                added.append(perm)
        self._dispatch_permission_events("attached", added)
        return self

    def revoke_permission_to(self, *perms: Permission | str) -> Self:
        guard = self.default_guard_name
        targets: set[tuple[str, str]] = set()
        for p in perms:
            coerced = _coerce_permission(p, guard=guard)
            targets.add((coerced.name, coerced.guard_name))
        removed = [p for p in self.permissions if (p.name, p.guard_name) in targets]
        self.permissions = [p for p in self.permissions if (p.name, p.guard_name) not in targets]
        self._dispatch_permission_events("detached", removed)
        return self

    def sync_permissions(self, perms: Sequence[Permission | str]) -> Self:
        guard = self.default_guard_name
        self.permissions = [_coerce_permission(p, guard=guard) for p in perms]
        return self

    def has_permission_to(self, permission: Permission | str, *, guard: str | None = None) -> bool:
        """Return True when the model holds the given permission directly or via a role.

        Also checks wildcard patterns (``"*"``, ``"resource.*"``,
        ``"res1,res2.action1,action2"``) held by the model.

        For role-granted permissions to be checked, roles must be loaded with their
        nested permissions relationship. The required eager-load pattern is::

            User.with_("roles.permissions", "permissions").where(...).first()

        If ``role.permissions`` is a lazy-loaded SQLAlchemy proxy and the session is
        closed, accessing it raises ``MissingGreenlet``. This method catches only that
        error and treats the role's permissions as empty rather than crashing.
        """
        target = (
            permission
            if isinstance(permission, Permission)
            else _MODEL_TYPES.permission_model(
                name=permission,
                guard_name=guard or self.default_guard_name,
            )
        )
        _check_guard(target.guard_name, guard)

        wildcards = getattr(self, "wildcard_permission", True)

        if any(_perm_matches(p, target, wildcards=wildcards) for p in self.permissions):
            return True

        roles: list[Role] = getattr(self, "roles", []) or []
        for role in roles:
            try:
                role_perms: list[Permission] = role.permissions
            except MissingGreenlet:
                role_perms = []
            if any(_perm_matches(p, target, wildcards=wildcards) for p in role_perms):
                return True
        return False

    def has_any_permission(self, *perms: Permission | str) -> bool:
        return any(self.has_permission_to(p) for p in perms)

    def has_all_permissions(self, *perms: Permission | str) -> bool:
        return all(self.has_permission_to(p) for p in perms)

    def get_all_permissions(self) -> list[Permission]:
        seen: set[tuple[str, str]] = set()
        out: list[Permission] = []
        for p in self.permissions:
            key = (p.name, p.guard_name)
            if key not in seen:
                seen.add(key)
                out.append(p)
        roles: list[Role] = getattr(self, "roles", []) or []
        for role in roles:
            try:
                role_perms: list[Permission] = role.permissions
            except MissingGreenlet:
                role_perms = []
            for p in role_perms:
                key = (p.name, p.guard_name)
                if key not in seen:
                    seen.add(key)
                    out.append(p)
        return out

    def get_permission_names(self) -> list[str]:
        return [p.name for p in self.get_all_permissions()]

    def get_direct_permissions(self) -> list[Permission]:
        """Return only permissions granted directly to this model (not via roles)."""
        return list(self.permissions)

    def get_permissions_via_roles(self) -> list[Permission]:
        """Return permissions inherited through roles (not directly granted)."""
        seen: set[tuple[str, str]] = set()
        out: list[Permission] = []
        roles: list[Role] = getattr(self, "roles", []) or []
        for role in roles:
            try:
                role_perms: list[Permission] = role.permissions
            except MissingGreenlet:
                role_perms = []
            for p in role_perms:
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
        from sqlalchemy import select  # noqa: PLC0415

        perm_name = permission.name if isinstance(permission, Permission) else permission
        pk = _primary_key_column(cls)
        subq = (
            select(cast(ModelHasPermission.model_id, Integer))
            .join(Permission, Permission.id == ModelHasPermission.permission_id)
            .where(
                Permission.name == perm_name,
                Permission.guard_name == guard,
                ModelHasPermission.model_type == cls.__name__,
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
        from sqlalchemy import select  # noqa: PLC0415

        perm_name = permission.name if isinstance(permission, Permission) else permission
        pk = _primary_key_column(cls)
        subq = (
            select(cast(ModelHasPermission.model_id, Integer))
            .join(Permission, Permission.id == ModelHasPermission.permission_id)
            .where(
                Permission.name == perm_name,
                Permission.guard_name == guard,
                ModelHasPermission.model_type == cls.__name__,
            )
        )
        result = await session.execute(select(cls).where(~pk.in_(subq)))
        return result.scalars().all()


# Spatie parity: Role can manage its own permissions via HasPermissions methods.
# Applied here (end of module) to break the circular-import cycle: models.py
# → traits.py → models.py. Role.permissions is already writable (viewonly=False).
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
    "_dispatch_permission_events",
)
for _method_name in _HP_METHODS:
    setattr(Role, _method_name, HasPermissions.__dict__[_method_name])


# Spatie parity: Permission can manage its own roles via HasRoles methods.
# Permission.roles is defined in models.py as a writable relationship.
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


# ── Relationship factory helpers (ADR-094) ────────────────────────────────────


def make_roles_relationship(
    model_getter: Callable[[], type[Any]],
    *,
    model_type: str,
) -> Any:
    """Build a ``roles`` relationship for a model with an integer primary key.

    The pivot table stores ``model_id`` as ``VARCHAR(36)``.  For integer-PK
    models the join must cast the pivot column to ``INTEGER``; this factory
    handles that internally so the consuming model needs no ``cast()`` call
    and no ``# type: ignore[attr-defined]``.

    Example::

        class User(Model, HasRoles):
            id: Mapped[int] = id_()
            roles: Mapped[list[Role]] = make_roles_relationship(
                lambda: User, model_type="User"
            )
    """

    def _primaryjoin() -> ColumnElement[bool]:
        model_cls = model_getter()
        pk_col = model_cls.__table__.c["id"]
        # Cast the integer PK to VARCHAR so foreign() wraps the raw model_id
        # column. This lets _StringId.process_bind_param run on INSERT, avoiding
        # asyncpg's strict int-vs-str rejection on the VARCHAR column.
        return and_(
            foreign(ModelHasRole.__table__.c.model_id) == cast(pk_col, String),
            ModelHasRole.__table__.c.model_type == model_type,
        )

    return relationship(
        Role,
        secondary=ModelHasRole.__table__,
        primaryjoin=_primaryjoin,
        secondaryjoin=foreign(ModelHasRole.__table__.c.role_id) == Role.id,
        viewonly=False,
        lazy="selectin",
        default_factory=list,
        init=False,
    )


def make_permissions_relationship(
    model_getter: Callable[[], type[Any]],
    *,
    model_type: str,
) -> Any:
    """Build a ``permissions`` relationship for a model with an integer primary key.

    Mirrors :func:`make_roles_relationship` for the direct-grant pivot.
    """

    def _primaryjoin() -> ColumnElement[bool]:
        model_cls = model_getter()
        pk_col = model_cls.__table__.c["id"]
        return and_(
            foreign(ModelHasPermission.__table__.c.model_id) == cast(pk_col, String),
            ModelHasPermission.__table__.c.model_type == model_type,
        )

    return relationship(
        Permission,
        secondary=ModelHasPermission.__table__,
        primaryjoin=_primaryjoin,
        secondaryjoin=foreign(ModelHasPermission.__table__.c.permission_id) == Permission.id,
        viewonly=False,
        lazy="selectin",
        default_factory=list,
        init=False,
    )
