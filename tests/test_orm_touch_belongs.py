"""ORM (doc 07) — touch + where_belongs_to."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class Post(Model):
    __timestamps__: ClassVar = True
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]


class Comment(Model):
    __fields__: ClassVar = {"post_id": int, "body": str}
    __fillable__: ClassVar = ["post_id", "body"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Post, Comment):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_touch_persists_updated_at() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="Hello")
        await post.touch()
        assert post.updated_at is not None
        fresh = await Post.find(post.id)
        assert fresh is not None
        assert fresh.updated_at == post.updated_at  # persisted
    finally:
        await db.dispose()


async def test_where_belongs_to_filters_by_parent() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="A")
        other = await Post.create(title="B")
        await Comment.create(post_id=post.id, body="on-a")
        await Comment.create(post_id=other.id, body="on-b")

        rows = await Comment.where_belongs_to(post).get()
        assert {c.body for c in rows} == {"on-a"}
    finally:
        await db.dispose()
