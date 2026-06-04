"""MorphOne/MorphMany query + eager integration.

MorphOne/MorphMany now resolve as relations, so they work with:
- `with_` — batched eager load (one query for all parents).
- `where_has` / `has` / `doesnt_have` — EXISTS subquery with the morph type predicate.
- `with_count` — per-parent count column.
- `Model.load` — lazy batched load onto an existing instance."""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, id_, integer, string
from arvel.database.orm import MorphMany, MorphOne
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi028Comment(Model):
    __tablename__ = "wi028_comments"
    id: int = id_()
    body: str = string(200)
    commentable_type: str = string(60)
    commentable_id: int = integer()


class Wi028Image(Model):
    __tablename__ = "wi028_images"
    id: int = id_()
    url: str = string(200)
    imageable_type: str = string(60)
    imageable_id: int = integer()


class Wi028Post(Model):
    __tablename__ = "wi028_posts"
    id: int = id_()
    title: str = string(120)

    comments: ClassVar[MorphMany[Wi028Comment]] = MorphMany(Wi028Comment, name="commentable")
    image: ClassVar[MorphOne[Wi028Image]] = MorphOne(Wi028Image, name="imageable")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


async def _make_comment(post: Wi028Post, body: str) -> Wi028Comment:
    comment: Wi028Comment = await Wi028Comment.create(
        body=body, commentable_type="Wi028Post", commentable_id=post.id
    )
    return comment


async def _make_image(post: Wi028Post, url: str) -> Wi028Image:
    image: Wi028Image = await Wi028Image.create(
        url=url, imageable_type="Wi028Post", imageable_id=post.id
    )
    return image


class TestEagerWith:
    async def test_morph_many_batches_in_one_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        p2 = await Wi028Post.create(title="B")
        await _make_comment(p1, "a1")
        await _make_comment(p1, "a2")
        await _make_comment(p2, "b1")

        from sqlalchemy import event

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            posts = await Wi028Post.query().with_("comments").get()
            # 1 for posts + 1 batched for all comments = 2.
            assert counter.count == 2
            before = counter.count
            counts = {p.title: len(p.comments) for p in posts}
            assert counter.count == before  # served from cache
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)
        assert counts == {"A": 2, "B": 1}

    async def test_morph_one_eager(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        await _make_image(p1, "/a.png")
        posts = await Wi028Post.query().with_("image").get()
        assert posts[0].image is not None
        assert posts[0].image.url == "/a.png"


class TestWhereHas:
    async def test_where_has_filters_to_parents_with_children(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="has")
        await Wi028Post.create(title="none")
        await _make_comment(p1, "hi")

        titles = [p.title for p in await Wi028Post.query().where_has("comments").get()]
        assert titles == ["has"]

    async def test_where_has_with_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="match")
        p2 = await Wi028Post.create(title="other")
        await _make_comment(p1, "keep")
        await _make_comment(p2, "skip")

        titles = [
            p.title
            for p in await Wi028Post.query()
            .where_has("comments", lambda q: q.where(Wi028Comment.__table__.c.body == "keep"))
            .get()
        ]
        assert titles == ["match"]

    async def test_doesnt_have(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="has")
        await Wi028Post.create(title="empty")
        await _make_comment(p1, "x")

        titles = [p.title for p in await Wi028Post.query().doesnt_have("comments").get()]
        assert titles == ["empty"]


class TestWithCount:
    async def test_with_count_adds_column(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        await _make_comment(p1, "a1")
        await _make_comment(p1, "a2")

        posts = (
            await Wi028Post.query()
            .with_count("comments")
            .where(Wi028Post.__table__.c.id == p1.id)
            .get()
        )
        assert posts[0].comments_count == 2


class TestModelLoad:
    async def test_load_morph_many_onto_instance(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        await _make_comment(p1, "a1")
        fresh = await Wi028Post.find(p1.id)
        assert fresh is not None
        await fresh.load("comments")
        assert len(fresh.comments) == 1
