"""Relationship aggregate completeness.

with_avg/with_min/with_exists, pivot-aware with_sum, aggregate aliasing + constraint closures,
and instance load_count/load_sum/load_aggregate/load_exists."""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, boolean, foreign_id, id_, integer, relationship, string
from arvel.database.orm import BelongsToMany
from arvel.database.query import QueryBuilder
from sqlalchemy import Column, ForeignKey, Integer, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

wi034_post_tags = Table(
    "wi034_post_tags",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("wi034_posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("wi034_tags.id"), primary_key=True),
)


class Wi034Tag(Model):
    __tablename__ = "wi034_tags"
    id: int = id_()
    name: str = string(80)
    weight: int = integer(default=0)


class Wi034Post(Model):
    __tablename__ = "wi034_posts"
    id: int = id_()
    title: str = string(120)
    comments: list[Wi034Comment] = relationship(
        "Wi034Comment", back_populates="post", init=False, default_factory=list
    )
    tags: ClassVar[BelongsToMany[Wi034Tag]] = BelongsToMany(
        Wi034Tag, table=wi034_post_tags, foreign_key="post_id", related_foreign_key="tag_id"
    )


class Wi034Comment(Model):
    __tablename__ = "wi034_comments"
    id: int = id_()
    body: str = string(200)
    rating: int = integer(default=0)
    spam: bool = boolean(default=False)
    post_id: int | None = foreign_id("wi034_posts.id", nullable=True)
    post: Wi034Post | None = relationship("Wi034Post", back_populates="comments", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _seed_post(title: str, ratings: list[int]) -> Wi034Post:
    post: Wi034Post = await Wi034Post.create(title=title)
    for r in ratings:
        await Wi034Comment.create(body=f"r{r}", post_id=post.id, rating=r)
    return post


class TestEagerAggregates:
    async def test_with_avg(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await _seed_post("p", [2, 4, 6])
        rows = (
            await Wi034Post.query()
            .with_avg("comments", "rating")
            .where(Wi034Post.__table__.c.id == p.id)
            .get()
        )
        assert rows[0].comments_avg_rating == 4

    async def test_with_min(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await _seed_post("p", [3, 7, 5])
        rows = (
            await Wi034Post.query()
            .with_min("comments", "rating")
            .where(Wi034Post.__table__.c.id == p.id)
            .get()
        )
        assert rows[0].comments_min_rating == 3

    async def test_with_exists(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        with_c = await _seed_post("has", [1])
        without_c = await Wi034Post.create(title="none")
        rows = await Wi034Post.query().with_exists("comments").get()
        by_id = {r.id: r for r in rows}
        assert bool(by_id[with_c.id].comments_exists) is True
        assert bool(by_id[without_c.id].comments_exists) is False


class TestPivotAwareSum:
    async def test_sum_over_belongs_to_many(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi034Post.create(title="p")
        t1 = await Wi034Tag.create(name="a", weight=10)
        t2 = await Wi034Tag.create(name="b", weight=15)
        await post.tags.attach(t1.id)
        await post.tags.attach(t2.id)

        rows = (
            await Wi034Post.query()
            .with_sum("tags", "weight")
            .where(Wi034Post.__table__.c.id == post.id)
            .get()
        )
        assert rows[0].tags_sum_weight == 25


class TestAliasAndConstraint:
    async def test_count_alias(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await _seed_post("p", [1, 2])
        rows = (
            await Wi034Post.query()
            .with_count("comments as comment_total")
            .where(Wi034Post.__table__.c.id == p.id)
            .get()
        )
        assert rows[0].comment_total == 2

    async def test_count_with_constraint(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await Wi034Post.create(title="p")
        await Wi034Comment.create(body="ham", post_id=p.id, spam=False)
        await Wi034Comment.create(body="ham2", post_id=p.id, spam=False)
        await Wi034Comment.create(body="spam", post_id=p.id, spam=True)

        rows = (
            await Wi034Post.query()
            .with_count(
                "comments",
                constraint=lambda q: q.where(Wi034Comment.__table__.c.spam == False),  # noqa: E712
            )
            .where(Wi034Post.__table__.c.id == p.id)
            .get()
        )
        assert rows[0].comments_count == 2

    async def test_sum_alias_and_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p = await Wi034Post.create(title="p")
        await Wi034Comment.create(body="a", post_id=p.id, rating=5, spam=False)
        await Wi034Comment.create(body="b", post_id=p.id, rating=3, spam=True)

        rows = (
            await Wi034Post.query()
            .with_sum(
                "comments",
                "rating",
                alias="ham_score",
                constraint=lambda q: q.where(Wi034Comment.__table__.c.spam == False),  # noqa: E712
            )
            .where(Wi034Post.__table__.c.id == p.id)
            .get()
        )
        assert rows[0].ham_score == 5


class TestInstanceLoaders:
    async def test_load_count(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await _seed_post("p", [1, 2, 3])
        value = await p.load_count("comments")
        assert value == 3
        assert p.comments_count == 3

    async def test_load_sum(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p = await _seed_post("p", [10, 20])
        value = await p.load_sum("comments", "rating")
        assert value == 30
        assert p.comments_sum_rating == 30

    async def test_load_exists(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        empty = await Wi034Post.create(title="empty")
        assert bool(await empty.load_exists("comments")) is False
        assert bool(empty.comments_exists) is False

    async def test_load_aggregate_avg_with_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p = await Wi034Post.create(title="p")
        await Wi034Comment.create(body="a", post_id=p.id, rating=4, spam=False)
        await Wi034Comment.create(body="b", post_id=p.id, rating=8, spam=False)
        await Wi034Comment.create(body="c", post_id=p.id, rating=100, spam=True)

        def ham_only(q: QueryBuilder[Any]) -> QueryBuilder[Any]:
            return q.where(Wi034Comment.__table__.c.spam == False)  # noqa: E712

        value = await p.load_aggregate("comments", "avg", "rating", constraint=ham_only)
        assert value == 6
        assert p.comments_avg_rating == 6
