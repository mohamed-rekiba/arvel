"""BelongsToMany parity (Laravel): pivot/query methods that were absent — count, where/order_by on the
related model, toggle, sync_without_detaching, update_existing_pivot — plus a fix so attach() accepts
extra pivot columns (the synthetic pivot Table now declares them)."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver


class Role(Model):
    __table_name__ = "roles"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "level": int}
    __fillable__: ClassVar[list[str]] = ["name", "level"]


class Account(Model):
    __table_name__ = "accounts"
    __fields__: ClassVar[dict[str, Any]] = {"name": str}
    __fillable__: ClassVar[list[str]] = ["name"]

    def roles(self) -> Any:
        return self.belongs_to_many(Role, "role_account", "account_id", "role_id")


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Role, Account):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(
        sa.text("CREATE TABLE role_account (account_id INTEGER, role_id INTEGER, assigned_by TEXT)")
    )
    return db


async def test_count_where_order_by() -> None:
    db = await _db()
    try:
        acc = await Account.create(name="Ada")
        admin = await Role.create(name="admin", level=10)
        editor = await Role.create(name="editor", level=5)
        await Role.create(name="viewer", level=1)
        await acc.roles().attach(admin.id)
        await acc.roles().attach(editor.id)
        assert await acc.roles().count() == 2
        # where() constrains the RELATED model query within the pivot-filtered set
        assert [r.name for r in await acc.roles().where("level", ">=", 10).get()] == ["admin"]
        assert [r.name for r in await acc.roles().order_by("level", "desc").get()] == [
            "admin",
            "editor",
        ]
    finally:
        await db.dispose()


async def test_sync_without_detaching_and_toggle() -> None:
    db = await _db()
    try:
        acc = await Account.create(name="Ada")
        admin = await Role.create(name="admin", level=10)
        editor = await Role.create(name="editor", level=5)
        viewer = await Role.create(name="viewer", level=1)
        await acc.roles().attach(admin.id)
        await acc.roles().attach(editor.id)
        # sync_without_detaching adds the new one, keeps the rest
        await acc.roles().sync_without_detaching([admin.id, viewer.id])
        assert sorted(r.name for r in await acc.roles().get()) == ["admin", "editor", "viewer"]
        # toggle: present → detached, absent → attached
        await acc.roles().toggle([admin.id, viewer.id])  # both present → both detached
        assert sorted(r.name for r in await acc.roles().get()) == ["editor"]
    finally:
        await db.dispose()


async def test_attach_with_pivot_data_and_update_existing_pivot() -> None:
    db = await _db()
    try:
        acc = await Account.create(name="Ada")
        editor = await Role.create(name="editor", level=5)
        await acc.roles().attach(editor.id, assigned_by="initial")  # extra pivot column
        first = await acc.roles().with_pivot("assigned_by").get()
        assert first[0]._attributes["pivot"]["assigned_by"] == "initial"
        await acc.roles().update_existing_pivot(editor.id, assigned_by="system")
        again = await acc.roles().with_pivot("assigned_by").get()
        assert again[0]._attributes["pivot"]["assigned_by"] == "system"
    finally:
        await db.dispose()
