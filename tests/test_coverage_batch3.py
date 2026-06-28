"""Coverage — Builder query branches (operators, 2-arg where, errors, lock, chunk, count)."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver

nums = sa.Table(
    "nums",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
    sa.Column("age", sa.Integer),
    sa.Column("active", sa.Boolean),
)


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(nums))
    for i in range(1, 6):
        await Builder(nums, db).insert({"name": f"A{i}", "age": 10 + i, "active": i % 2 == 0})
    return db


async def test_like_and_comparison_operators() -> None:
    db = await _db()
    try:
        like = await Builder(nums, db).where("name", "like", "A%").get()
        assert len(like) == 5
        ge = await Builder(nums, db).where("age", ">=", 13).get()
        assert {r["age"] for r in ge} == {13, 14, 15}
    finally:
        await db.dispose()


async def test_two_arg_where_equality() -> None:
    db = await _db()
    try:
        rows = await Builder(nums, db).where("active", True).get()  # 2-arg form
        assert all(r["active"] for r in rows)
    finally:
        await db.dispose()


async def test_count_scalar() -> None:
    db = await _db()
    try:
        assert await Builder(nums, db).count() == 5
    finally:
        await db.dispose()


async def test_chunk_by_id_with_sync_callback() -> None:
    db = await _db()
    try:
        sizes: list[int] = []
        await Builder(nums, db).chunk_by_id(2, lambda rows: sizes.append(len(rows)))  # sync cb
        assert sizes == [2, 2, 1]
    finally:
        await db.dispose()


def test_shared_lock_sets_mode() -> None:
    builder = Builder(nums).shared_lock()
    assert builder._lock == "shared"


def test_where_has_without_model_raises() -> None:
    with pytest.raises(RuntimeError, match="model-bound"):
        Builder(nums).where_has("posts")


async def test_get_without_resolver_raises() -> None:
    with pytest.raises(RuntimeError, match="resolver"):
        await Builder(nums).get()


def test_or_where_has_is_a_builder() -> None:
    # exercises or_where_has wiring on a model-bound builder
    from arvel.database import Model

    class Widget(Model):
        __fields__: dict[str, Any] = {"name": str, "widget_id": int}

        def parts(self) -> object:
            return self.has_many(Widget)

    builder = Widget.or_where_has("parts")
    assert isinstance(builder, Builder)
