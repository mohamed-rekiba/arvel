"""arvel.auth.permissions — RBAC roles & permissions (Spatie laravel-permission parity).

``Role``/``Permission`` are arvel models; the ``HasRoles`` mixin (combined with the app's
user model) assigns roles, grants direct permissions, and resolves effective permissions
(direct plus via-role) through the pivot tables ``model_has_roles`` /
``model_has_permissions`` / ``role_has_permissions``. Built on the ORM (arvel.database —
a declared layered edge, doc 17). Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, ClassVar

from arvel.database import Model


def _pivot(name: str, *columns: str) -> Any:
    import sqlalchemy as sa

    cols: list[Any] = []
    for column in columns:
        column_type: Any = sa.Integer if column.endswith("_id") else sa.String
        cols.append(sa.Column(column, column_type))
    return sa.Table(name, sa.MetaData(), *cols)


class Role(Model):
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "guard_name": str}
    __fillable__: ClassVar[list[str]] = ["name", "guard_name"]

    async def give_permission_to(self, *names: str) -> Role:
        from arvel.database.builder import Builder

        pivot = _pivot("role_has_permissions", "role_id", "permission_id")
        for name in names:
            permission = await Permission.where(name=name).first()
            if permission is not None:
                await Builder(pivot, type(self)._resolve()).insert(
                    {"role_id": self.id, "permission_id": permission.id}
                )
        return self

    async def permissions(self) -> list[Any]:
        """The permissions granted to this role (Spatie ``$role->permissions``)."""
        from arvel.database.builder import Builder

        pivot = _pivot("role_has_permissions", "role_id", "permission_id")
        rows = await Builder(pivot, type(self)._resolve()).where("role_id", "=", self.id).get()
        ids = [row["permission_id"] for row in rows]
        result: list[Any] = await Permission.where_in("id", ids).get() if ids else []
        return result


class Permission(Model):
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "guard_name": str}
    __fillable__: ClassVar[list[str]] = ["name", "guard_name"]


class HasRoles:
    """Mixin for the app's user model: ``class User(Authenticatable, HasRoles)``."""

    def _as_model(self) -> Any:
        return self  # at runtime this *is* a Model; typed loosely for the mixin

    def _morph(self) -> tuple[str, Any]:
        model = self._as_model()
        return type(model).__name__, model._attributes[model.__primary_key__]

    def _connection(self) -> Any:
        # NB: call Model's _resolve() method (not the _resolver ClassVar, which Model
        # exposes under that name and which would shadow a same-named mixin method).
        return self._as_model()._resolve()

    def _roles_pivot(self, *, teams: bool) -> Any:
        cols = ["role_id", "model_type", "model_id"]
        if teams:
            cols.append("team_id")
        return _pivot("model_has_roles", *cols)

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
        from arvel.database.builder import Builder

        morph_type, morph_id = self._morph()
        pivot = self._roles_pivot(teams=team is not None)
        for name in names:
            role = await Role.where(name=name).first()
            if role is not None:
                row: dict[str, Any] = {
                    "role_id": role.id,
                    "model_type": morph_type,
                    "model_id": morph_id,
                }
                if team is not None:
                    row["team_id"] = team
                await Builder(pivot, self._connection()).insert(row)
        self.flush_permission_cache()
        return self

    async def remove_role(self, name: str, team: Any = None) -> HasRoles:
        """Revoke a role from this model (Spatie ``removeRole``). No-op if the role isn't assigned."""
        from arvel.database.builder import Builder

        morph_type, morph_id = self._morph()
        role = await Role.where(name=name).first()
        if role is not None:
            query = (
                Builder(self._roles_pivot(teams=team is not None), self._connection())
                .where("role_id", "=", role.id)
                .where("model_type", "=", morph_type)
                .where("model_id", "=", morph_id)
            )
            if team is not None:
                query = query.where("team_id", "=", team)
            await query.delete()
        self.flush_permission_cache()
        return self

    async def roles(self, team: Any = None) -> list[Any]:
        from arvel.database.builder import Builder

        morph_type, morph_id = self._morph()
        query = (
            Builder(self._roles_pivot(teams=team is not None), self._connection())
            .where("model_type", "=", morph_type)
            .where("model_id", "=", morph_id)
        )
        if team is not None:
            query = query.where("team_id", "=", team)
        rows = await query.get()
        role_ids = [row["role_id"] for row in rows]
        if not role_ids:
            return []
        result: list[Any] = await Role.where_in("id", role_ids).get()
        return result

    async def has_role(self, name: str, team: Any = None) -> bool:
        if name in self._carried_idp_roles():
            return True
        return any(role.name == name for role in await self.roles(team))

    async def give_permission_to(self, *names: str) -> HasRoles:
        from arvel.database.builder import Builder

        morph_type, morph_id = self._morph()
        pivot = _pivot("model_has_permissions", "permission_id", "model_type", "model_id")
        for name in names:
            permission = await Permission.where(name=name).first()
            if permission is not None:
                await Builder(pivot, self._connection()).insert(
                    {"permission_id": permission.id, "model_type": morph_type, "model_id": morph_id}
                )
        self.flush_permission_cache()
        return self

    async def _effective_permission_ids(self) -> set[Any]:
        from arvel.database.builder import Builder

        morph_type, morph_id = self._morph()
        direct = await (
            Builder(
                _pivot("model_has_permissions", "permission_id", "model_type", "model_id"),
                self._connection(),
            )
            .where("model_type", "=", morph_type)
            .where("model_id", "=", morph_id)
            .get()
        )
        ids = {row["permission_id"] for row in direct}
        role_ids = [role.id for role in await self.roles()]
        if role_ids:
            via = await (
                Builder(
                    _pivot("role_has_permissions", "role_id", "permission_id"), self._connection()
                )
                .where_in("role_id", role_ids)
                .get()
            )
            ids |= {row["permission_id"] for row in via}
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
        perms: list[Any] = await Permission.where_in("id", list(ids)).get() if ids else []
        resolved = {p.name for p in perms}
        # DR-0011: union permissions granted via ephemeral IdP-derived roles (not persisted).
        idp_roles = self._carried_idp_roles()
        if idp_roles:
            resolved |= await self._permission_names_for_role_names(idp_roles)
        object.__setattr__(self, "_perm_cache", resolved)
        return resolved

    async def _permission_names_for_role_names(self, names: set[str]) -> set[str]:
        from arvel.database.builder import Builder

        role_records = await Role.where_in("name", list(names)).get()
        role_ids = [role.id for role in role_records]
        if not role_ids:
            return set()
        via = await (
            Builder(_pivot("role_has_permissions", "role_id", "permission_id"), self._connection())
            .where_in("role_id", role_ids)
            .get()
        )
        perm_ids = {row["permission_id"] for row in via}
        perms: list[Any] = await Permission.where_in("id", list(perm_ids)).get() if perm_ids else []
        return {perm.name for perm in perms}

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
