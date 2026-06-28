"""Query builder — ``select_raw`` + ``group_by`` for grouped aggregates (spec 08 §42,
the MaterializedView surface ``Order.select_raw(...).group_by(...)``). Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Sale(Model):
    __fields__ = {"region": str, "amount": int}
    __fillable__ = ["region", "amount"]


async def _table(model: type[Model], db: ConnectionResolver) -> None:
    model.set_connection(db)
    await db.execute(sa.schema.CreateTable(model.__table__))


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    await _table(Sale, db)
    await Sale.create(region="us", amount=10)
    await Sale.create(region="us", amount=30)
    await Sale.create(region="eu", amount=5)
    return db


async def test_group_by_with_select_raw_aggregates_rows() -> None:
    db = await _seed()
    try:
        stmt = (
            Sale.select_raw("region, sum(amount) AS total")
            .group_by("region")
            .order_by("region")
            .to_select()
        )
        rows = await db.fetch_all(stmt)
        assert [dict(r) for r in rows] == [
            {"region": "eu", "total": 5},
            {"region": "us", "total": 40},
        ]
    finally:
        await db.dispose()


async def test_group_by_multiple_columns() -> None:
    db = await _seed()
    try:
        stmt = Sale.select_raw("region, count(*) AS n").group_by("region").to_select()
        rows = await db.fetch_all(stmt)
        by_region = {r["region"]: r["n"] for r in rows}
        assert by_region == {"us": 2, "eu": 1}
    finally:
        await db.dispose()


async def test_select_raw_only_suppresses_default_star() -> None:
    # select_raw without select() should emit just the raw expression, not SELECT *
    db = await _seed()
    try:
        stmt = Sale.select_raw("count(*) AS c").to_select()
        compiled = str(stmt.compile())
        assert "count(*)" in compiled
        assert ".region" not in compiled  # no full-table star
    finally:
        await db.dispose()
