"""Catalog ORM behaviors (eager-loading, serialization, conditional filtering, pagination) against
real PostgreSQL — SQLite's looser typing can hide gaps these depend on.
"""

from __future__ import annotations

import enum
from typing import ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model

pytestmark = pytest.mark.integration


class ProductStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"


class Category(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]

    def products(self) -> object:
        return self.has_many(Product)


class Product(Model):
    __fields__: ClassVar = {"category_id": int, "name": str, "status": str}
    __fillable__: ClassVar = ["category_id", "name", "status"]
    __casts__: ClassVar = {"status": ProductStatus}

    def category(self) -> object:
        return self.belongs_to(Category)

    def variants(self) -> object:
        return self.has_many(Variant)


class Variant(Model):
    __fields__: ClassVar = {"product_id": int, "sku": str, "stock": int}
    __fillable__: ClassVar = ["product_id", "sku", "stock"]


async def _setup(url: str) -> ConnectionResolver:
    db = ConnectionResolver({"default": {"url": url}})
    for model in (Category, Product, Variant):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_catalog_eager_load_and_serialization_on_postgres(postgres_url: str) -> None:
    db = await _setup(postgres_url)
    try:
        shirts = await Category.create(name="Shirts")
        active = await Product.create(
            category_id=shirts.id, name="Aero", status=ProductStatus.ACTIVE
        )
        await Product.create(category_id=shirts.id, name="Hidden", status=ProductStatus.DRAFT)
        await Variant.create(product_id=active.id, sku="AERO-S", stock=5)
        await Variant.create(product_id=active.id, sku="AERO-M", stock=8)

        product = await Product.with_("category", "variants").where("name", "Aero").first()
        data = product.to_dict()
        assert data["status"] == "active"
        assert data["category"]["name"] == "Shirts"
        assert sorted(v["sku"] for v in data["variants"]) == ["AERO-M", "AERO-S"]

        only_active = (
            await Product.query()
            .when(True, lambda q, _: q.where("status", ProductStatus.ACTIVE.value))
            .get()
        )
        assert [p.name for p in only_active] == ["Aero"]

        page = await Category.with_("products").paginate(per_page=10)
        as_dict = page.to_dict()
        assert as_dict["total"] == 1
        assert as_dict["data"][0]["products"][0]["name"] in {"Aero", "Hidden"}
    finally:
        for model in (Variant, Product, Category):
            await db.execute(sa.schema.DropTable(model.__table__))
        await db.dispose()
