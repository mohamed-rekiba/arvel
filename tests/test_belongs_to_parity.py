"""BelongsTo parity (Laravel): the inverse relation is a query builder too (where/order_by proxy to the
owner query), and associate/dissociate set/clear the child's foreign key."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver


class Country(Model):
    __table_name__ = "countries"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "continent": str}
    __fillable__: ClassVar[list[str]] = ["name", "continent"]


class City(Model):
    __table_name__ = "cities"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "country_id": int}
    __fillable__: ClassVar[list[str]] = ["name", "country_id"]

    def country(self) -> Any:
        return self.belongs_to(Country, "country_id")


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Country, City):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_belongs_to_query_proxy() -> None:
    db = await _db()
    try:
        fr = await Country.create(name="France", continent="EU")
        city = await City.create(name="Paris", country_id=fr.id)
        # where/order_by proxy to the FK-constrained owner query
        assert (await city.country().where("continent", "=", "EU").first()).name == "France"
        assert await city.country().where("continent", "=", "AS").first() is None
        assert (
            await city.country().get()
        ).name == "France"  # get() still resolves the single owner
        assert hasattr(city.country(), "_private") is False  # honest hasattr, no recursion
    finally:
        await db.dispose()


async def test_associate_sets_foreign_key() -> None:
    db = await _db()
    try:
        fr = await Country.create(name="France", continent="EU")
        de = await Country.create(name="Germany", continent="EU")
        city = await City.create(name="Paris", country_id=fr.id)
        returned = city.country().associate(de)
        assert city.country_id == de.id  # FK set on the child
        assert returned is city  # returns the child
        await city.save()
        assert (await City.find(city.id)).country_id == de.id  # persists on save
    finally:
        await db.dispose()


async def test_dissociate_clears_foreign_key() -> None:
    db = await _db()
    try:
        fr = await Country.create(name="France", continent="EU")
        city = await City.create(name="Paris", country_id=fr.id)
        returned = city.country().dissociate()
        assert city.country_id is None
        assert returned is city
    finally:
        await db.dispose()
