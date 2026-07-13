"""Coverage — Builder query breadth: select/distinct/where_*/aggregates/paginate (doc 07)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver

nums = sa.Table(
    "nums",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("val", sa.Integer),
    sa.Column("grp", sa.String),
)


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(nums))
    for i in range(1, 6):
        await Builder(nums, db).insert({"val": i, "grp": "a" if i % 2 else None})
    return db


async def test_select_distinct_order_limit_offset() -> None:
    db = await _setup()
    try:
        rows = (
            await Builder(nums, db).select("val").order_by("val", "desc").limit(2).offset(1).get()
        )
        assert [r["val"] for r in rows] == [4, 3]
        grps = await Builder(nums, db).select("grp").distinct().get()
        assert len(grps) >= 1
    finally:
        await db.dispose()


async def test_where_variants() -> None:
    db = await _setup()
    try:
        assert len(await Builder(nums, db).where_in("val", [1, 2]).get()) == 2
        ors = await Builder(nums, db).where("val", "=", 1).or_where("val", "=", 5).get()
        assert {r["val"] for r in ors} == {1, 5}
        assert len(await Builder(nums, db).where_null("grp").get()) == 2  # even vals
        assert len(await Builder(nums, db).where_not_null("grp").get()) == 3
    finally:
        await db.dispose()


async def test_aggregates_and_exists() -> None:
    db = await _setup()
    try:
        assert await Builder(nums, db).count() == 5
        assert await Builder(nums, db).sum("val") == 15
        assert await Builder(nums, db).avg("val") == 3
        assert await Builder(nums, db).min("val") == 1
        assert await Builder(nums, db).max("val") == 5
        assert await Builder(nums, db).where("val", "=", 3).exists() is True
        assert await Builder(nums, db).where("val", "=", 99).exists() is False
    finally:
        await db.dispose()


async def test_paginate() -> None:
    db = await _setup()
    try:
        page = await Builder(nums, db).order_by("val").paginate(per_page=2, page=2)
        assert page.per_page() == 2
        assert page.current_page() == 2
        assert page.count() == 2
        assert page.total() == 5
    finally:
        await db.dispose()
