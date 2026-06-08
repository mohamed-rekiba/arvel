"""whereHas / has / withCount must honour the related model's soft-delete scope.

Laravel never counts trashed related rows in has/whereHas/withCount, and
withCount raises for relations the model doesn't define."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from arvel.database import Model, SoftDeletes, Timestamps, field, id_, relationship, string
from arvel.database.exceptions import UnknownRelationError
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, ForeignKey, Integer, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Blog(Model):
    __tablename__ = "rcsd_blogs"
    id: int = id_()
    name: str = string(80)
    comments: list[Comment] = relationship(
        "Comment", back_populates="blog", init=False, default_factory=list
    )


class Comment(Model, Timestamps, SoftDeletes):
    __tablename__ = "rcsd_comments"
    id: int = id_()
    body: str = string(200)
    blog_id: int | None = field(foreign_key="rcsd_blogs.id", default=None)
    blog: Blog | None = relationship("Blog", back_populates="comments", init=False)


rcsd_blog_label = Table(
    "rcsd_blog_labels",
    Model.metadata,
    Column("blog_id", Integer, ForeignKey("rcsd_blogs.id"), primary_key=True),
    Column("label_id", Integer, ForeignKey("rcsd_labels.id"), primary_key=True),
)


class Label(Model, Timestamps, SoftDeletes):
    __tablename__ = "rcsd_labels"
    id: int = id_()
    name: str = string(80)


class TaggedBlog(Model):
    __tablename__ = "rcsd_tagged_blogs"
    id: int = id_()
    name: str = string(80)
    labels: ClassVar[BelongsToMany[Label]] = BelongsToMany(
        Label, table=rcsd_blog_label, foreign_key="blog_id", related_foreign_key="label_id"
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestSoftDeleteScopeInRelationCounts:
    async def test_has_ignores_trashed_related(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        blog = await Blog.create(name="kept")
        empty = await Blog.create(name="empty")
        c = await Comment.create(body="hi", blog_id=blog.id)
        await c.delete()  # soft delete the only comment

        # Both blogs now have zero *live* comments.
        rows = await Blog.has("comments").all()
        assert [r.name for r in rows] == []
        assert empty.id is not None

    async def test_where_has_ignores_trashed_related(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        blog = await Blog.create(name="kept")
        live = await Comment.create(body="live", blog_id=blog.id)
        gone = await Comment.create(body="gone", blog_id=blog.id)
        await gone.delete()

        rows = await Blog.where_has("comments").all()
        assert [r.name for r in rows] == ["kept"]
        assert live.deleted_at is None

    async def test_with_count_excludes_trashed_related(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        blog = await Blog.create(name="kept")
        await Comment.create(body="a", blog_id=blog.id)
        gone = await Comment.create(body="b", blog_id=blog.id)
        await gone.delete()

        rows = await Blog.with_count("comments").all()
        row: Any = rows[0]
        assert row.comments_count == 1

    async def test_with_count_excludes_trashed_pivot_target(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tb = await TaggedBlog.create(name="t")
        live = await Label.create(name="live")
        dead = await Label.create(name="dead")
        await tb.labels.attach(live.id)
        await tb.labels.attach(dead.id)
        await dead.delete()

        rows = await TaggedBlog.with_count("labels").all()
        row: Any = rows[0]
        assert row.labels_count == 1


class TestSoftDeleteScopeInEagerLoads:
    """Eager with_() honours the related soft-delete scope, like Laravel and with_count."""

    async def test_eager_with_excludes_trashed_sa_relationship(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        blog = await Blog.create(name="kept")
        await Comment.create(body="live", blog_id=blog.id)
        gone = await Comment.create(body="gone", blog_id=blog.id)
        await gone.delete()

        session.expire_all()
        rows = await Blog.with_("comments").all()
        loaded = next(b for b in rows if b.id == blog.id)
        assert sorted(c.body for c in loaded.comments) == ["live"]

    async def test_eager_with_excludes_trashed_pivot_target(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tb = await TaggedBlog.create(name="t")
        live = await Label.create(name="live")
        dead = await Label.create(name="dead")
        await tb.labels.attach(live.id)
        await tb.labels.attach(dead.id)
        await dead.delete()

        session.expire_all()
        rows = await TaggedBlog.with_("labels").all()
        loaded = next(b for b in rows if b.id == tb.id)
        labels = await loaded.labels.all()
        assert sorted(label.name for label in labels) == ["live"]

    async def test_eager_with_trashed_constraint_includes_trashed(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        blog = await Blog.create(name="kept")
        await Comment.create(body="live", blog_id=blog.id)
        gone = await Comment.create(body="gone", blog_id=blog.id)
        await gone.delete()

        session.expire_all()
        rows = await Blog.with_({"comments": lambda q: q.with_trashed()}).all()
        loaded = next(b for b in rows if b.id == blog.id)
        assert sorted(c.body for c in loaded.comments) == ["gone", "live"]

    async def test_lazy_pivot_excludes_trashed_target(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tb = await TaggedBlog.create(name="t")
        live = await Label.create(name="live")
        dead = await Label.create(name="dead")
        await tb.labels.attach(live.id)
        await tb.labels.attach(dead.id)
        await dead.delete()

        labels = await tb.labels.all()
        assert sorted(label.name for label in labels) == ["live"]


class TestWithCountUnknownRelation:
    async def test_raises_for_unknown_relation(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        with pytest.raises(UnknownRelationError):
            await Blog.with_count("nope").all()
