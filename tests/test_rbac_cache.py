"""Auth/RBAC (doc 15) — permission cache: memoize effective permissions, flush on change."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.auth import HasRoles, Permission, Role
from arvel.database import ConnectionResolver, Model


class Agent(Model, HasRoles):
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
    for model in (Agent, Role, Permission):
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


async def test_permissions_are_memoized_after_first_check() -> None:
    db = await _setup()
    try:
        user = await Agent.create(name="ada")
        assert not await user.has_permission_to("edit")  # computes + caches the (empty) set
        assert user.__dict__.get("_perm_cache") is not None  # memoized
    finally:
        await db.dispose()


async def test_grant_flushes_cache_so_new_permission_is_seen() -> None:
    db = await _setup()
    try:
        await Permission.create(name="edit", guard_name="web")
        user = await Agent.create(name="ada")
        assert not await user.has_permission_to("edit")  # caches empty
        await user.give_permission_to("edit")  # flushes the cache
        assert await user.has_permission_to("edit")  # recomputed → granted
    finally:
        await db.dispose()


async def test_manual_flush_recomputes() -> None:
    db = await _setup()
    try:
        user = await Agent.create(name="ada")
        await user.has_permission_to("edit")  # populate cache
        user.flush_permission_cache()
        assert user.__dict__.get("_perm_cache") is None
    finally:
        await db.dispose()
