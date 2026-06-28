"""Coverage — ApplicationBuilder, Blueprint column modifiers, model scopes/update_or_create/to_dict."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.database.schema import Blueprint
from arvel.kernel.application import Application, ApplicationBuilder


def test_application_builder_fluent_methods() -> None:
    builder = ApplicationBuilder(Application())
    builder.with_routing(web="routes/web.py")
    builder.with_middlewares([object()])
    builder.with_exceptions(lambda e: e)
    assert isinstance(builder.create(), Application)


def test_column_definition_modifiers() -> None:
    blueprint = Blueprint("things")
    col = blueprint.string("name").nullable().not_null().unique().index()
    assert col is not None
    blueprint.integer("count")


class Item(Model):
    __fields__: ClassVar = {"sku": str, "price": int}
    __fillable__: ClassVar = ["sku", "price"]


async def test_update_or_create_both_branches() -> None:
    db = ConnectionResolver()
    Item.set_connection(db)
    await db.execute(sa.schema.CreateTable(Item.__table__))
    try:
        created = await Item.update_or_create({"sku": "X"}, {"price": 1})  # create branch
        assert created.price == 1
        updated = await Item.update_or_create({"sku": "X"}, {"price": 2})  # update branch
        assert updated.price == 2
        assert len(await Item.get()) == 1  # same row, updated
    finally:
        await db.dispose()


def test_without_global_scopes_returns_query() -> None:
    class Acct(Model):
        __fields__: ClassVar = {"a": int}

    Acct.add_global_scope("only_active", lambda q: q)
    try:
        assert Acct.without_global_scopes() is not None
    finally:
        Acct.__global_scopes__ = {}


def test_to_dict_respects_hidden() -> None:
    class User(Model):
        __fields__: ClassVar = {"name": str, "secret": str}
        __hidden__: ClassVar = ["secret"]

    user = User()
    object.__setattr__(user, "_attributes", {"name": "ada", "secret": "shh"})
    data: dict[str, Any] = user.to_dict()
    assert data["name"] == "ada"
    assert "secret" not in data
