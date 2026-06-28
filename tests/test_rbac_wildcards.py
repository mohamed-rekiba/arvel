"""Auth/RBAC (doc 15) — wildcard permissions: posts.* grants posts.edit; * grants all."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.auth import HasRoles, Permission, Role
from arvel.database import ConnectionResolver, Model


class Staff(Model, HasRoles):
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
    for model in (Staff, Role, Permission):
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


async def test_dotted_wildcard_grants_namespace() -> None:
    db = await _setup()
    try:
        await Permission.create(name="posts.*", guard_name="web")
        user = await Staff.create(name="ada")
        await user.give_permission_to("posts.*")

        assert await user.has_permission_to("posts.edit")
        assert await user.has_permission_to("posts.delete")
        assert await user.has_permission_to("posts")  # the bare namespace
        assert not await user.has_permission_to("users.edit")  # different namespace
    finally:
        await db.dispose()


async def test_superadmin_star_grants_everything() -> None:
    db = await _setup()
    try:
        await Permission.create(name="*", guard_name="web")
        user = await Staff.create(name="root")
        await user.give_permission_to("*")

        assert await user.has_permission_to("anything.at.all")
        assert await user.has_permission_to("billing.refund")
    finally:
        await db.dispose()


async def test_exact_permission_still_required_without_wildcard() -> None:
    db = await _setup()
    try:
        await Permission.create(name="reports.view", guard_name="web")
        user = await Staff.create(name="viewer")
        await user.give_permission_to("reports.view")

        assert await user.has_permission_to("reports.view")
        assert not await user.has_permission_to("reports.delete")  # no wildcard granted
    finally:
        await db.dispose()
