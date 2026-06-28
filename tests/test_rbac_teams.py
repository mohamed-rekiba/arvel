"""Auth/RBAC (doc 15) — team-scoped roles (Spatie teams parity)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.auth import HasRoles, Permission, Role
from arvel.database import ConnectionResolver, Model


class TeamUser(Model, HasRoles):
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
    for model in (TeamUser, Role, Permission):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    # teams parity: model_has_roles carries a team_id
    await db.execute(
        sa.schema.CreateTable(
            _pivot("model_has_roles", "role_id", "model_type", "model_id", "team_id")
        )
    )
    return db


async def test_roles_are_scoped_per_team() -> None:
    db = await _setup()
    try:
        await Role.create(name="editor", guard_name="web")
        await Role.create(name="admin", guard_name="web")
        user = await TeamUser.create(name="ada")

        await user.assign_role("editor", team=1)
        await user.assign_role("admin", team=2)

        assert await user.has_role("editor", team=1)
        assert not await user.has_role("editor", team=2)  # not in team 2
        assert await user.has_role("admin", team=2)
        assert not await user.has_role("admin", team=1)
    finally:
        await db.dispose()


async def test_unscoped_has_role_sees_any_team() -> None:
    db = await _setup()
    try:
        await Role.create(name="editor", guard_name="web")
        user = await TeamUser.create(name="ada")
        await user.assign_role("editor", team=5)

        assert await user.has_role("editor")  # team=None → matches across teams
    finally:
        await db.dispose()
