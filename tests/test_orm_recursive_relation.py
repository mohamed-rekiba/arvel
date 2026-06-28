"""ORM — recursive relations (adjacency-list trees): Model.recursive() → descendants/
ancestors with depth (.get() flat, .tree().get() nested). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Category(Model):
    __fields__ = {"parent_id": int, "name": str}
    __fillable__ = ["parent_id", "name"]

    def children(self) -> object:
        return self.has_many(Category, foreign_key="parent_id")

    def descendants(self) -> object:
        return self.recursive(Category, "parent_id")

    def ancestors(self) -> object:
        return self.recursive(Category, "parent_id", direction="up")


async def _seed() -> tuple[ConnectionResolver, dict[str, Category]]:
    db = ConnectionResolver()
    Category.set_connection(db)
    await db.execute(sa.schema.CreateTable(Category.__table__))
    # electronics(1) → phones(2) → smartphones(3);  electronics(1) → laptops(4);  toys(5) root
    n: dict[str, Category] = {}
    n["electronics"] = await Category.create(name="electronics")
    n["toys"] = await Category.create(name="toys")
    n["phones"] = await Category.create(name="phones", parent_id=n["electronics"].id)
    n["smartphones"] = await Category.create(name="smartphones", parent_id=n["phones"].id)
    n["laptops"] = await Category.create(name="laptops", parent_id=n["electronics"].id)
    return db, n


async def test_descendants_flat_with_depth() -> None:
    db, n = await _seed()
    try:
        rows = await n["electronics"].descendants().get()
        assert {c.name: c.depth for c in rows} == {"phones": 1, "laptops": 1, "smartphones": 2}
    finally:
        await db.dispose()


async def test_ancestors_flat_with_depth() -> None:
    db, n = await _seed()
    try:
        rows = await n["smartphones"].ancestors().get()
        assert {c.name: c.depth for c in rows} == {"phones": 1, "electronics": 2}
    finally:
        await db.dispose()


async def test_descendants_tree_is_nested_under_children() -> None:
    db, n = await _seed()
    try:
        tree = await n["electronics"].descendants().tree().get()
        # roots = direct children; smartphones nests under phones via "children"
        by_name = {node["name"]: node for node in tree}
        assert set(by_name) == {"phones", "laptops"}
        assert [c["name"] for c in by_name["phones"]["children"]] == ["smartphones"]
        assert by_name["laptops"]["children"] == []
    finally:
        await db.dispose()


async def test_ancestors_tree_nests_under_parents() -> None:
    db, n = await _seed()
    try:
        tree = await n["smartphones"].ancestors().tree().get()
        # nearest ancestor (phones) is the root; electronics nests under it via "parents"
        assert len(tree) == 1
        root = tree[0]
        assert root["name"] == "phones"
        assert "parents" in root and "children" not in root
        assert [a["name"] for a in root["parents"]] == ["electronics"]
        assert root["parents"][0]["parents"] == []
    finally:
        await db.dispose()


async def test_tree_accepts_custom_key() -> None:
    db, n = await _seed()
    try:
        tree = await n["electronics"].descendants().tree(key="subitems").get()
        phones = next(node for node in tree if node["name"] == "phones")
        assert [c["name"] for c in phones["subitems"]] == ["smartphones"]
    finally:
        await db.dispose()


async def test_empty_when_leaf_has_no_descendants() -> None:
    db, n = await _seed()
    try:
        assert await n["smartphones"].descendants().get() == []
    finally:
        await db.dispose()


async def test_with_eager_loads_descendants_batched() -> None:
    db, _ = await _seed()
    try:
        # one batched recursive CTE loads every category's subtree — no N+1
        cats = {c.name: c for c in await Category.with_("descendants").get()}
        elec = {m.name: m.depth for m in cats["electronics"].relation("descendants")}
        assert elec == {"phones": 1, "laptops": 1, "smartphones": 2}
        assert {m.name for m in cats["phones"].relation("descendants")} == {"smartphones"}
        assert cats["toys"].relation("descendants") == []  # a childless root
    finally:
        await db.dispose()


async def test_with_eager_loads_ancestors_batched() -> None:
    db, _ = await _seed()
    try:
        cats = {c.name: c for c in await Category.with_("ancestors").get()}
        sp = {m.name: m.depth for m in cats["smartphones"].relation("ancestors")}
        assert sp == {"phones": 1, "electronics": 2}
        assert cats["electronics"].relation("ancestors") == []  # a root has no ancestors
    finally:
        await db.dispose()
