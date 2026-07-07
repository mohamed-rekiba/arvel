"""Bulk delete through the query builder must respect soft-deletes: a builder bound to a
SoftDeletes model stamps ``deleted_at`` (matching the instance path), and only an explicit
``force_delete()`` removes the rows."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, SoftDeletes


class Widget(Model, SoftDeletes):
    __fields__ = {"name": str, "bucket": str}
    __fillable__ = ["name", "bucket"]


class Gadget(Model):
    __fields__ = {"name": str, "bucket": str}
    __fillable__ = ["name", "bucket"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Widget, Gadget):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_bulk_delete_soft_deletes_matching_rows() -> None:
    db = await _setup()
    try:
        await Widget.create(name="a", bucket="drop")
        await Widget.create(name="b", bucket="drop")
        await Widget.create(name="c", bucket="keep")

        affected = await Widget.where("bucket", "=", "drop").delete()
        assert affected.rowcount == 2

        # default scope hides them, but the rows are still there (soft, not hard)
        assert sorted(w.name for w in await Widget.all()) == ["c"]
        trashed = await Widget.only_trashed().get()
        assert sorted(w.name for w in trashed) == ["a", "b"]
        assert all(w.deleted_at is not None for w in trashed)
    finally:
        await db.dispose()


async def test_bulk_delete_hard_deletes_a_plain_model() -> None:
    db = await _setup()
    try:
        await Gadget.create(name="a", bucket="drop")
        await Gadget.create(name="b", bucket="keep")

        await Gadget.where("bucket", "=", "drop").delete()
        assert sorted(g.name for g in await Gadget.all()) == ["b"]
    finally:
        await db.dispose()


async def test_prune_hard_removes_even_a_soft_delete_model() -> None:
    # prune reclaims storage — the rows prunable() matches must be gone for good, not stamped.
    db = await _setup()
    try:
        await Widget.create(name="old", bucket="drop")
        await Widget.prune()  # default prunable() matches all live rows
        assert await Widget.with_trashed().count() == 0
    finally:
        await db.dispose()


async def test_bulk_force_delete_removes_soft_delete_rows() -> None:
    db = await _setup()
    try:
        await Widget.create(name="a", bucket="drop")
        await Widget.create(name="b", bucket="drop")

        await Widget.where("bucket", "=", "drop").force_delete()
        # gone for good — not even with_trashed sees them
        assert await Widget.with_trashed().count() == 0
    finally:
        await db.dispose()
