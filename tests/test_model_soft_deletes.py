"""ORM depth (doc 07) — SoftDeletes mixin. Test-first."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, SoftDeletes


class Post(Model, SoftDeletes):
    __fields__ = {"title": str}
    __fillable__ = ["title"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Post.set_connection(db)
    await db.execute(sa.schema.CreateTable(Post.__table__))
    return db


def test_table_has_deleted_at_column() -> None:
    assert "deleted_at" in Post.__table__.c


async def test_soft_delete_excludes_from_default_queries() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="x")
        await post.delete()  # soft
        assert post.trashed()
        assert await Post.all() == []  # default scope hides trashed
        assert len(await Post.with_trashed().get()) == 1
        assert len(await Post.only_trashed().get()) == 1
    finally:
        await db.dispose()


async def test_restore() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="y")
        await post.delete()
        await post.restore()
        assert not post.trashed()
        assert len(await Post.all()) == 1
    finally:
        await db.dispose()


async def test_force_delete_removes_row() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="z")
        await post.force_delete()
        assert len(await Post.with_trashed().get()) == 0
    finally:
        await db.dispose()
