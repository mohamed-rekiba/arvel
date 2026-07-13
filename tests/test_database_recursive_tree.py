"""Recursive CTE returns a FULL tree of descendants."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver

categories = sa.Table(
    "categories",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("parent_id", sa.Integer),
    sa.Column("name", sa.String),
)


async def test_recursive_cte_returns_full_subtree() -> None:
    db = ConnectionResolver()
    try:
        await db.execute(sa.schema.CreateTable(categories))
        # root(1) → electronics; 2 phones (←1); 3 smartphones (←2); 4 laptops (←1); 5 toys (root)
        rows = [
            {"id": 1, "parent_id": None, "name": "electronics"},
            {"id": 2, "parent_id": 1, "name": "phones"},
            {"id": 3, "parent_id": 2, "name": "smartphones"},
            {"id": 4, "parent_id": 1, "name": "laptops"},
            {"id": 5, "parent_id": None, "name": "toys"},
        ]
        for row in rows:
            await db.execute(categories.insert().values(**row))

        # WITH RECURSIVE: anchor = the root; recursive arm joins children to the CTE.
        stmt = Builder(categories).recursive_cte(
            "tree",
            anchor=Builder(categories).where(id=1),
            recursive=lambda cte: sa.select(categories).join(
                cte, categories.c.parent_id == cte.c.id
            ),
        )
        found = await db.fetch_all(stmt)
        names = {row["name"] for row in found}
        # the WHOLE subtree under electronics — across all depths — not just direct children
        assert names == {"electronics", "phones", "smartphones", "laptops"}
        assert "toys" not in names  # a separate root is excluded
    finally:
        await db.dispose()
