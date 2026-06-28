"""Integration (doc 08) — `t.vector` works as a real pgvector column on Postgres (CREATE EXTENSION
vector), incl. a nearest-neighbour query. Requires the [vector] extra + Docker."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.database.schema import Blueprint

pytestmark = pytest.mark.integration

pytest.importorskip("pgvector")


async def test_vector_column_and_knn_on_postgres(pgvector_url: str) -> None:
    db = ConnectionResolver({"default": {"url": pgvector_url}})
    try:
        await db.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

        bp = Blueprint("items")
        bp.id()
        bp.string("name")
        bp.vector("embedding", 3)
        table = bp.to_table()
        await db.execute(sa.schema.CreateTable(table))

        await db.execute(table.insert().values(name="a", embedding=[1.0, 0.0, 0.0]))
        await db.execute(table.insert().values(name="b", embedding=[0.0, 1.0, 0.0]))
        await db.execute(table.insert().values(name="c", embedding=[0.9, 0.1, 0.0]))

        # nearest neighbour to [1,0,0] by L2 distance — should be "a", then "c"
        query = (
            sa.select(table.c.name)
            .order_by(table.c.embedding.l2_distance([1.0, 0.0, 0.0]))
            .limit(2)
        )
        rows = await db.fetch_all(query)
        assert [r["name"] for r in rows] == ["a", "c"]
    finally:
        await db.dispose()
