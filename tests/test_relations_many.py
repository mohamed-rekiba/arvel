"""ORM depth (doc 07) — belongs_to_many + pivot (attach/detach/sync). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Role(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class User(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def roles(self) -> object:
        return self.belongs_to_many(Role)


_md = sa.MetaData()
role_user = sa.Table(
    "role_user", _md, sa.Column("user_id", sa.Integer), sa.Column("role_id", sa.Integer)
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (User, Role):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(role_user))
    return db


async def test_attach_and_get() -> None:
    db = await _setup()
    try:
        user = await User.create(name="ada")
        admin = await Role.create(name="admin")
        editor = await Role.create(name="editor")
        await user.roles().attach(admin.id)
        await user.roles().attach(editor.id)
        roles = await user.roles().get()
        assert {r.name for r in roles} == {"admin", "editor"}
    finally:
        await db.dispose()


async def test_detach() -> None:
    db = await _setup()
    try:
        user = await User.create(name="bob")
        admin = await Role.create(name="admin")
        editor = await Role.create(name="editor")
        await user.roles().attach(admin.id)
        await user.roles().attach(editor.id)
        await user.roles().detach(admin.id)
        assert {r.name for r in await user.roles().get()} == {"editor"}
    finally:
        await db.dispose()


async def test_sync_replaces_set() -> None:
    db = await _setup()
    try:
        user = await User.create(name="cleo")
        admin = await Role.create(name="admin")
        editor = await Role.create(name="editor")
        await user.roles().attach(editor.id)
        await user.roles().sync([admin.id])
        assert {r.name for r in await user.roles().get()} == {"admin"}
    finally:
        await db.dispose()


async def test_empty_relation_returns_empty_list() -> None:
    db = await _setup()
    try:
        user = await User.create(name="dee")
        assert await user.roles().get() == []
    finally:
        await db.dispose()
