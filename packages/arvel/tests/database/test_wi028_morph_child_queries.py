"""WI-arvel-028 — Epic 007 Story 3: MorphOne/MorphMany query + eager integration.

MorphOne/MorphMany now resolve as relations, so they work with:
- `with_()` — batched eager load (one query for all parents).
- `where_has` / `has` / `doesnt_have` — EXISTS subquery with the morph type predicate.
- `with_count` — per-parent count column.
- `Model.load()` — lazy batched load onto an existing instance.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model
from arvel.database.orm import MorphMany, MorphOne
from sqlalchemy import Integer, String
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Wi028Comment(Model):
    __tablename__ = "wi028_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str] = mapped_column(String(200), nullable=False)
    commentable_type: Mapped[str] = mapped_column(String(60), nullable=False)
    commentable_id: Mapped[int] = mapped_column(Integer, nullable=False)


class Wi028Image(Model):
    __tablename__ = "wi028_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    url: Mapped[str] = mapped_column(String(200), nullable=False)
    imageable_type: Mapped[str] = mapped_column(String(60), nullable=False)
    imageable_id: Mapped[int] = mapped_column(Integer, nullable=False)


class Wi028Post(Model):
    __tablename__ = "wi028_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), nullable=False)

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


class TestEagerWith:
    async def test_morph_many_batches_in_one_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        p2 = await Wi028Post.create(title="B")
        await p1.comments.create(body="a1")
        await p1.comments.create(body="a2")
        await p2.comments.create(body="b1")

        from sqlalchemy import event

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            posts = await Wi028Post.query().with_("comments").get()
            # 1 for posts + 1 batched for all comments = 2.
            assert counter.count == 2
            before = counter.count
            counts = {p.title: len(await p.comments.all()) for p in posts}
            assert counter.count == before  # served from cache
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)
        assert counts == {"A": 2, "B": 1}

    async def test_morph_one_eager(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        await p1.image.create(url="/a.png")
        posts = await Wi028Post.query().with_("image").get()
        img = await posts[0].image
        assert img is not None
        assert img.url == "/a.png"


class TestWhereHas:
    async def test_where_has_filters_to_parents_with_children(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="has")
        await Wi028Post.create(title="none")
        await p1.comments.create(body="hi")

        titles = [p.title for p in await Wi028Post.query().where_has("comments").get()]
        assert titles == ["has"]

    async def test_where_has_with_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="match")
        p2 = await Wi028Post.create(title="other")
        await p1.comments.create(body="keep")
        await p2.comments.create(body="skip")

        titles = [
            p.title
            for p in await Wi028Post.query()
            .where_has("comments", lambda q: q.where(Wi028Comment.body == "keep"))
            .get()
        ]
        assert titles == ["match"]

    async def test_doesnt_have(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="has")
        await Wi028Post.create(title="empty")
        await p1.comments.create(body="x")

        titles = [p.title for p in await Wi028Post.query().doesnt_have("comments").get()]
        assert titles == ["empty"]


class TestWithCount:
    async def test_with_count_adds_column(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        await p1.comments.create(body="a1")
        await p1.comments.create(body="a2")

        posts = await Wi028Post.query().with_count("comments").where(Wi028Post.id == p1.id).get()
        assert posts[0].comments_count == 2


class TestModelLoad:
    async def test_load_morph_many_onto_instance(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi028Post.create(title="A")
        await p1.comments.create(body="a1")
        fresh = await Wi028Post.find(p1.id)
        assert fresh is not None
        await fresh.load("comments")
        # Accessor now reads from the cache load() populated.
        assert len(await fresh.comments.all()) == 1
