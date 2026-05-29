"""WI-arvel-069 — Epic 049 Story 6: has/where_has/doesnt_have for BelongsToMany."""

from __future__ import annotations

from typing import ClassVar

from arvel.database import Model
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

post_tag_wi069 = Table(
    "wi069_post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("wi069_posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("wi069_tags.id", ondelete="CASCADE"), primary_key=True),
    Column("label", String(40), nullable=True),
)


class Wi069Tag(Model):
    __tablename__ = "wi069_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class Wi069Post(Model):
    __tablename__ = "wi069_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    tags: ClassVar[BelongsToMany[Wi069Tag]] = BelongsToMany(
        Wi069Tag,
        table=post_tag_wi069,
        foreign_key="post_id",
        related_foreign_key="tag_id",
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestWhereHasBelongsToMany:
    async def test_returns_posts_with_at_least_one_tag(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tagged = await Wi069Post.create(title="Tagged")
        await Wi069Post.create(title="Bare")
        tag = await Wi069Tag.create(name="news")
        await tagged.tags.attach(tag.id)

        rows = await Wi069Post.where_has("tags").all()
        assert len(rows) == 1
        assert rows[0].title == "Tagged"

    async def test_constraint_filters_related_rows(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        featured_post = await Wi069Post.create(title="Featured")
        other_post = await Wi069Post.create(title="Other")
        featured = await Wi069Tag.create(name="featured")
        misc = await Wi069Tag.create(name="misc")
        await featured_post.tags.attach(featured.id)
        await other_post.tags.attach(misc.id)

        rows = (
            await Wi069Post.query()
            .where_has("tags", lambda q: q.where(Wi069Tag.name == "featured"))
            .all()
        )
        assert len(rows) == 1
        assert rows[0].title == "Featured"


class TestHasBelongsToMany:
    async def test_count_operator_on_pivot_rows(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        prolific = await Wi069Post.create(title="Prolific")
        sparse = await Wi069Post.create(title="Sparse")
        t1 = await Wi069Tag.create(name="a")
        t2 = await Wi069Tag.create(name="b")
        t3 = await Wi069Tag.create(name="c")
        await prolific.tags.attach(t1.id)
        await prolific.tags.attach(t2.id)
        await prolific.tags.attach(t3.id)
        await sparse.tags.attach(t1.id)

        rows = await Wi069Post.has("tags", ">=", 2).all()
        assert len(rows) == 1
        assert rows[0].title == "Prolific"


class TestDoesntHaveBelongsToMany:
    async def test_returns_posts_without_tags(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        bare = await Wi069Post.create(title="Bare")
        tagged = await Wi069Post.create(title="Tagged")
        tag = await Wi069Tag.create(name="x")
        await tagged.tags.attach(tag.id)

        rows = await Wi069Post.doesnt_have("tags").all()
        assert len(rows) == 1
        assert rows[0].title == "Bare"
        assert bare.id == rows[0].id
