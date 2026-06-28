"""ORM gap-audit completion — D3 (to_json), D5 (__view__ read-only), D6 (recursive/from_cte)."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from arvel.database import Attribute, Builder, ConnectionResolver
from arvel.database.model import Model, ReadOnlyModelError


# --- D3: to_json ----------------------------------------------------------------
class Article(Model):
    __fields__ = {"title": str, "secret": str}
    __hidden__ = ["secret"]
    __appends__ = ["slug"]

    def slug(self) -> Attribute:
        return Attribute(get=lambda v, a: a["title"].lower().replace(" ", "-"))


def test_to_json_is_json_string_of_to_dict() -> None:
    art = Article(title="Hello World", secret="x")
    raw = art.to_json()
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert parsed == art.to_dict()


def test_to_json_honors_hidden_and_appends() -> None:
    parsed = json.loads(Article(title="Hi There", secret="nope").to_json())
    assert "secret" not in parsed  # __hidden__
    assert parsed["slug"] == "hi-there"  # __appends__ accessor


# --- D5: __view__ read-only model -----------------------------------------------
class ActiveUser(Model):
    __view__ = "active_users"
    __fields__ = {"name": str}


def test_view_model_reads_from_the_view() -> None:
    assert ActiveUser.__table__.name == "active_users"


async def test_view_model_blocks_writes() -> None:
    user = ActiveUser(name="ada")
    # every write path must raise — a missed one is a silent UPDATE against a view (B1)
    with pytest.raises(ReadOnlyModelError):
        await user.save()
    with pytest.raises(ReadOnlyModelError):
        await user.delete()
    with pytest.raises(ReadOnlyModelError):
        await user.force_delete()
    with pytest.raises(ReadOnlyModelError):
        await user.restore()
    with pytest.raises(ReadOnlyModelError):
        await user.touch()


# --- D6: low-level Builder.recursive_cte + from_cte -----------------------------
# (the ergonomic tree API lives in test_orm_recursive_relation.py via Model.recursive())
class Category(Model):
    __fields__ = {"parent_id": int, "name": str}


async def test_recursive_cte_and_from_cte_return_full_subtree() -> None:
    db = ConnectionResolver()
    Category.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Category.__table__))
        rows = [
            {"id": 1, "parent_id": None, "name": "electronics"},
            {"id": 2, "parent_id": 1, "name": "phones"},
            {"id": 3, "parent_id": 2, "name": "smartphones"},
            {"id": 4, "parent_id": 1, "name": "laptops"},
            {"id": 5, "parent_id": None, "name": "toys"},
        ]
        for row in rows:
            await db.execute(Category.__table__.insert().values(**row))

        tbl = Category.__table__
        base = Builder(tbl).where(id=1).to_select().cte("tree", recursive=True)
        recursive_cte = base.union_all(sa.select(tbl).join(base, tbl.c.parent_id == base.c.id))
        subtree = (
            await Builder(tbl, db, hydrate=Category._hydrate, model=Category)
            .from_cte(recursive_cte)
            .get()
        )

        names = {m.name for m in subtree}
        assert names == {"electronics", "phones", "smartphones", "laptops"}
        assert "toys" not in names
    finally:
        await db.dispose()
