"""Has-one-of-many (latest/oldest/of_many).

Two surfaces:
- Method style off `has_many`/`has_one`:
  `await post.has_many(Comment).latest_of_many("created_at")`.
- Descriptor style for eager loading: `HasOneOfMany(...)` resolves one row per parent through a
  single grouped subquery (`with_("latest_comment")`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from arvel.database import Model, id_, integer, string
from arvel.database import datetime as datetime_col
from arvel.database.orm import HasOneOfMany
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


class Wi030Comment(Model):
    __tablename__ = "wi030_comments"
    id: int = id_()
    body: str = string(200)
    wi030_post_id: int = integer()
    created_at: datetime = datetime_col(timezone=True)


class Wi030Post(Model):
    __tablename__ = "wi030_posts"
    id: int = id_()
    title: str = string(120)

    latest_comment: ClassVar[HasOneOfMany[Wi030Comment]] = HasOneOfMany(
        Wi030Comment, column="created_at", aggregate="max"
    )
    oldest_comment: ClassVar[HasOneOfMany[Wi030Comment]] = HasOneOfMany(
        Wi030Comment, column="created_at", aggregate="min"
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _comment(post: Wi030Post, body: str, minutes: int) -> Wi030Comment:
    comment: Wi030Comment = await Wi030Comment.create(
        body=body, wi030_post_id=post.id, created_at=_BASE + timedelta(minutes=minutes)
    )
    return comment


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


class TestMethodStyle:
    async def test_latest_and_oldest_of_many(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi030Post.create(title="p")
        await _comment(post, "first", 0)
        await _comment(post, "middle", 30)
        await _comment(post, "last", 60)

        latest = await post.has_many(Wi030Comment, foreign_key="wi030_post_id").latest_of_many(
            "created_at"
        )
        oldest = await post.has_many(Wi030Comment, foreign_key="wi030_post_id").oldest_of_many(
            "created_at"
        )
        assert latest is not None
        assert latest.body == "last"
        assert oldest is not None
        assert oldest.body == "first"

    async def test_of_many_no_rows_returns_none(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi030Post.create(title="empty")
        latest = await post.has_many(Wi030Comment, foreign_key="wi030_post_id").latest_of_many()
        assert latest is None


class TestDescriptorAccessor:
    async def test_lazy_accessor(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi030Post.create(title="p")
        await _comment(post, "a", 0)
        await _comment(post, "b", 10)

        latest = await post.latest_comment
        oldest = await post.oldest_comment
        assert latest is not None
        assert latest.body == "b"
        assert oldest is not None
        assert oldest.body == "a"

    async def test_lazy_accessor_none(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi030Post.create(title="p")
        assert await post.latest_comment is None


class TestDescriptorEager:
    async def test_with_picks_one_per_parent_in_one_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi030Post.create(title="p1")
        p2 = await Wi030Post.create(title="p2")
        await _comment(p1, "p1-old", 0)
        await _comment(p1, "p1-new", 50)
        await _comment(p2, "p2-old", 5)
        await _comment(p2, "p2-new", 40)

        from sqlalchemy import event

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            posts = await Wi030Post.with_("latest_comment").get()
            # 1 for posts + 1 grouped subquery for the latest comments = 2.
            assert counter.count == 2
            before = counter.count
            latest = {p.title: (await p.latest_comment) for p in posts}
            assert counter.count == before  # served from cache
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)

        assert latest["p1"] is not None
        assert latest["p1"].body == "p1-new"
        assert latest["p2"] is not None
        assert latest["p2"].body == "p2-new"

    async def test_with_oldest(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p1 = await Wi030Post.create(title="p1")
        await _comment(p1, "old", 0)
        await _comment(p1, "new", 90)

        posts = await Wi030Post.with_("oldest_comment").get()
        oldest = await posts[0].oldest_comment
        assert oldest is not None
        assert oldest.body == "old"
