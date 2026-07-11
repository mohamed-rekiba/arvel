"""arvel.auth.permissions — RBAC roles & permissions (Spatie's permission parity).

``Role``/``Permission`` are arvel models; the ``HasRoles`` mixin (combined with the app's user
model) assigns roles, grants direct permissions, and resolves effective permissions (direct plus
via-role) through the pivot tables ``model_has_roles`` / ``model_has_permissions`` /
``role_has_permissions`` — reached through arvel's own relations (``morph_to_many`` for the
polymorphic model pivots, ``belongs_to_many`` for role↔permission), never hand-rolled pivot SQL.
Built on the ORM (arvel.database — a declared layered edge, doc 17). Grounded in
knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, ClassVar

from arvel.database import Model


class Role(Model):
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "guard_name": str}
    __fillable__: ClassVar[list[str]] = ["name", "guard_name"]

    def permissions_relation(self) -> Any:
        """The role↔permission pivot as a ``belongs_to_many`` over ``role_has_permissions``."""
        return self.belongs_to_many(
            Permission,
            pivot="role_has_permissions",
            foreign_pivot_key="role_id",
            related_pivot_key="permission_id",
        )

    async def give_permission_to(self, *names: str) -> Role:
        relation = self.permissions_relation()
        for name in names:
            permission = await Permission.where(name=name).first()
            if permission is not None:
                await relation.attach(permission.id)
        return self

    async def permissions(self) -> list[Any]:
        """The permissions granted to this role (Spatie ``$role->permissions``)."""
        return list(await self.permissions_relation().get())


class Permission(Model):
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "guard_name": str}
    __fillable__: ClassVar[list[str]] = ["name", "guard_name"]


class HasRoles:
    """Mixin for the app's user model: ``class User(Authenticatable, HasRoles)``."""

    def _as_model(self) -> Any:
        return self  # at runtime this *is* a Model; typed loosely for the mixin

    def _roles_relation(self, *, team: Any = None) -> Any:
        """The model↔role pivot as a ``morph_to_many`` over ``model_has_roles``, optionally scoped
        to a team via the extra ``team_id`` pivot column."""
        relation = self._as_model().morph_to_many(Role, "model", pivot="model_has_roles")
        if team is not None:
            relation = relation.where_pivot("team_id", team)
        return relation

    def _direct_permissions_relation(self) -> Any:
        """The model↔permission pivot as a ``morph_to_many`` over ``model_has_permissions``."""
        return self._as_model().morph_to_many(Permission, "model", pivot="model_has_permissions")

    def set_idp_roles(self, names: Iterable[str]) -> None:
        """Carry ephemeral IdP-derived role names for this request (DR-0011).

        Resolved at login from the token's claim→role mapping and unioned with the user's
        persisted grants at check time — never written as membership.
        """
        object.__setattr__(self, "_idp_role_names", set(names))
        self.flush_permission_cache()

    def _carried_idp_roles(self) -> set[str]:
        carried = self.__dict__.get("_idp_role_names")
        return set(carried) if carried else set()

    async def assign_role(self, *names: str, team: Any = None) -> HasRoles:
        relation = self._roles_relation()
        for name in names:
            role = await Role.where(name=name).first()
            if role is not None:
                await relation.attach(role.id, **({"team_id": team} if team is not None else {}))
        self.flush_permission_cache()
        return self

    async def remove_role(self, name: str, team: Any = None) -> HasRoles:
        """Revoke a role from this model (Spatie ``removeRole``). No-op if the role isn't assigned."""
        role = await Role.where(name=name).first()
        if role is not None:
            relation = self._roles_relation()
            await relation.detach(role.id, **({"team_id": team} if team is not None else {}))
        self.flush_permission_cache()
        return self

    async def roles(self, team: Any = None) -> list[Any]:
        return list(await self._roles_relation(team=team).get())

    async def has_role(self, name: str, team: Any = None) -> bool:
        if name in self._carried_idp_roles():
            return True
        return any(role.name == name for role in await self.roles(team))

    async def give_permission_to(self, *names: str) -> HasRoles:
        relation = self._direct_permissions_relation()
        for name in names:
            permission = await Permission.where(name=name).first()
            if permission is not None:
                await relation.attach(permission.id)
        self.flush_permission_cache()
        return self

    async def _effective_permission_ids(self) -> set[Any]:
        direct = await self._direct_permissions_relation().get()
        ids = {p.id for p in direct}
        for role in await self.roles():
            ids |= {p.id for p in await role.permissions()}
        return ids

    def flush_permission_cache(self) -> None:
        """Drop the memoized effective-permission set (call after granting/revoking)."""
        object.__setattr__(self, "_perm_cache", None)

    async def _effective_permission_names(self) -> set[str]:
        cached = self.__dict__.get("_perm_cache")
        if cached is not None:
            names: set[str] = cached
            return names
        ids = await self._effective_permission_ids()
        perms: Sequence[Any] = await Permission.where_in("id", list(ids)).get() if ids else []
        resolved = {p.name for p in perms}
        # union in permissions granted via ephemeral IdP-derived roles (never persisted)
        idp_roles = self._carried_idp_roles()
        if idp_roles:
            resolved |= await self._permission_names_for_role_names(idp_roles)
        object.__setattr__(self, "_perm_cache", resolved)
        return resolved

    async def _permission_names_for_role_names(self, names: set[str]) -> set[str]:
        role_records = await Role.where_in("name", list(names)).get()
        resolved: set[str] = set()
        for role in role_records:
            resolved |= {perm.name for perm in await role.permissions()}
        return resolved

    @staticmethod
    def _permission_granted(granted: set[str], name: str) -> bool:
        """Exact, super-admin (``*``), or dotted-wildcard (``posts.*`` grants ``posts.edit``)."""
        if name in granted or "*" in granted:
            return True
        return any(
            g.endswith(".*") and (name == g[:-2] or name.startswith(g[:-1])) for g in granted
        )

    async def has_permission_to(self, name: str) -> bool:
        return self._permission_granted(await self._effective_permission_names(), name)


__all__ = ["HasRoles", "Permission", "Role"]
