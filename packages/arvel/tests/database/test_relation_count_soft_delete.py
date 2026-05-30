"""whereHas / has / withCount must honour the related model's soft-delete scope.

Laravel never counts trashed related rows in has/whereHas/withCount, and
withCount raises for relations the model doesn't define.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from arvel.database import Model, SoftDeletes, Timestamps
from arvel.database.exceptions import UnknownRelationError
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Blog(Model):
    __tablename__ = "rcsd_blogs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    comments: Mapped[list[Comment]] = relationship(
        "Comment", back_populates="blog", init=False, default_factory=list
    )


class Comment(Model, Timestamps, SoftDeletes):
    __tablename__ = "rcsd_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str] = mapped_column(String(200))
    blog_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rcsd_blogs.id"), default=None)
    blog: Mapped[Blog | None] = relationship("Blog", back_populates="comments", init=False)


rcsd_blog_label = Table(
    "rcsd_blog_labels",
    Model.metadata,
    Column("blog_id", Integer, ForeignKey("rcsd_blogs.id"), primary_key=True),
    Column("label_id", Integer, ForeignKey("rcsd_labels.id"), primary_key=True),
)


class Label(Model, Timestamps, SoftDeletes):
    __tablename__ = "rcsd_labels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))


class TaggedBlog(Model):
    __tablename__ = "rcsd_tagged_blogs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
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

        rows = await Blog.query().with_count("comments").all()
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

        rows = await TaggedBlog.query().with_count("labels").all()
        row: Any = rows[0]
        assert row.labels_count == 1


class TestWithCountUnknownRelation:
    async def test_raises_for_unknown_relation(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        with pytest.raises(UnknownRelationError):
            await Blog.query().with_count("nope").all()
