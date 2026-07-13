"""ORM (doc 07) — saving a child touches the parents named in __touches__."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.dates import Date
from arvel.testing import freeze_time


class Post(Model):
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]
    __timestamps__ = True


class Comment(Model):
    __fields__: ClassVar = {"post_id": int, "body": str}
    __fillable__: ClassVar = ["post_id", "body"]
    __timestamps__ = True
    __touches__: ClassVar = ["post"]

    def post(self):
        return self.belongs_to(Post)


async def _setup(db: ConnectionResolver, *models: type[Model]) -> None:
    for m in models:
        m.set_connection(db)
        await db.execute(sa.schema.CreateTable(m.__table__))


async def test_saving_child_touches_parent() -> None:
    db = ConnectionResolver()
    await _setup(db, Post, Comment)
    try:
        t1 = Date.parse("2026-01-01T00:00:00+00:00[UTC]")
        with freeze_time(t1):
            post = await Post.create(title="Hello")
        assert (await Post.find(post.id)).updated_at == t1  # timestamps read back as Date

        t2 = Date.parse("2026-02-02T00:00:00+00:00[UTC]")
        with freeze_time(t2):
            await Comment(post_id=post.id, body="hi").save()

        assert (await Post.find(post.id)).updated_at == t2  # parent touched to t2
    finally:
        await db.dispose()


async def test_no_touches_leaves_parent_untouched() -> None:
    db = ConnectionResolver()

    class Tag(Model):
        __fields__: ClassVar = {"post_id": int}
        __fillable__: ClassVar = ["post_id"]
        __timestamps__ = True

        def post(self):
            return self.belongs_to(Post)

    await _setup(db, Post, Tag)
    try:
        with freeze_time(Date.parse("2026-01-01T00:00:00+00:00[UTC]")):
            post = await Post.create(title="X")
        before = (await Post.find(post.id)).updated_at
        with freeze_time(Date.parse("2026-03-03T00:00:00+00:00[UTC]")):
            await Tag(post_id=post.id).save()  # Tag has no __touches__
        assert (await Post.find(post.id)).updated_at == before
    finally:
        await db.dispose()
