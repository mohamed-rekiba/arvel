"""`t.vector` works as a real pgvector column on Postgres, incl. a nearest-neighbour query."""

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

        # nearest neighbour to [1,0,0] by L2 distance
        query = (
            sa.select(table.c.name)
            .order_by(table.c.embedding.l2_distance([1.0, 0.0, 0.0]))
            .limit(2)
        )
        rows = await db.fetch_all(query)
        assert [r["name"] for r in rows] == ["a", "c"]
    finally:
        await db.dispose()


async def test_builder_similarity_clauses_on_postgres(pgvector_url: str) -> None:
    from arvel.database.builder import Builder

    db = ConnectionResolver({"default": {"url": pgvector_url}})
    try:
        await db.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

        bp = Blueprint("notes")
        bp.id()
        bp.string("name")
        bp.vector("embedding", 3)
        table = bp.to_table()
        await db.execute(sa.schema.CreateTable(table))
        for name, emb in (
            ("a", [1.0, 0.0, 0.0]),
            ("b", [0.0, 1.0, 0.0]),
            ("c", [0.9, 0.1, 0.0]),
        ):
            await db.execute(table.insert().values(name=name, embedding=emb))

        probe = [1.0, 0.0, 0.0]
        nearest = await Builder(table, db).order_by_similarity("embedding", probe).limit(2).get()
        assert [r["name"] for r in nearest] == ["a", "c"]  # cosine, nearest-first

        by_l2 = await Builder(table, db).order_by_similarity("embedding", probe, metric="l2").get()
        assert [r["name"] for r in by_l2] == ["a", "c", "b"]

        close = (
            await Builder(table, db)
            .where_vector_similar("embedding", probe, metric="l2", max_distance=0.5)
            .where("name", "!=", "zzz")  # composes with plain wheres
            .get()
        )
        assert sorted(r["name"] for r in close) == ["a", "c"]

        # wrong-dimension probe and insert are the driver's error, surfaced unmangled
        with pytest.raises(Exception, match=r"dimensions?"):
            await Builder(table, db).order_by_similarity("embedding", [1.0, 0.0]).get()
        with pytest.raises(Exception, match=r"dimensions?"):
            await db.execute(table.insert().values(name="short", embedding=[1.0]))
    finally:
        await db.dispose()
