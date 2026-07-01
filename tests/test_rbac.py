"""Auth/RBAC (doc 15) — HasRoles mixin + Role/Permission (Spatie parity). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.auth import HasRoles, Permission, Role
from arvel.database import ConnectionResolver, Model


class Member(Model, HasRoles):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


def _pivot(name: str, *cols: str) -> sa.Table:
    return sa.Table(
        name,
        sa.MetaData(),
        *[sa.Column(c, sa.Integer if c.endswith("_id") else sa.String) for c in cols],
    )


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Member, Role, Permission):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(
        sa.schema.CreateTable(_pivot("model_has_roles", "role_id", "model_type", "model_id"))
    )
    await db.execute(
        sa.schema.CreateTable(
            _pivot("model_has_permissions", "permission_id", "model_type", "model_id")
        )
    )
    await db.execute(
        sa.schema.CreateTable(_pivot("role_has_permissions", "role_id", "permission_id"))
    )
    return db


async def test_assign_role_and_has_role() -> None:
    db = await _setup()
    try:
        await Role.create(name="editor", guard_name="web")
        member = await Member.create(name="ada")
        await member.assign_role("editor")
        assert await member.has_role("editor")
        assert not await member.has_role("admin")
        assert {r.name for r in await member.roles()} == {"editor"}
    finally:
        await db.dispose()


async def test_remove_role_revokes() -> None:
    db = await _setup()
    try:
        await Role.create(name="editor", guard_name="web")
        member = await Member.create(name="ada")
        await member.assign_role("editor")
        assert await member.has_role("editor")
        await member.remove_role("editor")
        assert not await member.has_role("editor")
        assert {r.name for r in await member.roles()} == set()
        await member.remove_role("editor")  # idempotent no-op
    finally:
        await db.dispose()


async def test_permission_via_role() -> None:
    db = await _setup()
    try:
        editor = await Role.create(name="editor", guard_name="web")
        await Permission.create(name="edit-articles", guard_name="web")
        await editor.give_permission_to("edit-articles")
        member = await Member.create(name="bob")
        await member.assign_role("editor")
        assert await member.has_permission_to("edit-articles")  # inherited via role
        assert not await member.has_permission_to("delete-articles")
        assert {p.name for p in await editor.permissions()} == {
            "edit-articles"
        }  # role's own grants
    finally:
        await db.dispose()


async def test_direct_permission() -> None:
    db = await _setup()
    try:
        await Permission.create(name="publish", guard_name="web")
        member = await Member.create(name="cleo")
        await member.give_permission_to("publish")
        assert await member.has_permission_to("publish")  # granted directly
    finally:
        await db.dispose()


async def test_idp_derived_role_grants_permissions_via_union() -> None:
    """DR-0011: an ephemeral IdP-derived role grants its permissions with NO persisted assignment.

    Exercises the DB permission-union path (_permission_names_for_role_names): the role exists with
    a permission, but the member never assign_role()'d it — it comes only from the token at login.
    """
    db = await _setup()
    try:
        admin = await Role.create(name="admin", guard_name="web")
        await Permission.create(name="manage-users", guard_name="web")
        await admin.give_permission_to("manage-users")
        member = await Member.create(name="dora")

        member.set_idp_roles({"admin"})  # carried from the IdP token, not persisted
        assert await member.has_role("admin")  # union (in-memory)
        assert await member.has_permission_to("manage-users")  # union (via DB role->perm)
        assert not await member.has_permission_to("delete-everything")
        assert {r.name for r in await member.roles()} == set()  # no persisted membership
    finally:
        await db.dispose()
