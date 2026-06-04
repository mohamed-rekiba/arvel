"""MorphTo inverse relation.

- `comment.commentable` resolves the parent from `{name}_type` + `{name}_id`.
- `associate(model)` / `dissociate` set/clear both discriminator columns together.
- Eager loading over a list batches parents grouped by type — one query per distinct type."""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, id_, integer, string
from arvel.database.orm import MorphMany, MorphTo
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi027Comment(Model):
    __tablename__ = "wi027_comments"
    id: int = id_()
    body: str = string(200)
    commentable_type: str | None = string(60, nullable=True, default=None)
    commentable_id: int | None = integer(nullable=True, default=None)

    commentable: ClassVar[MorphTo[Any]] = MorphTo(name="commentable")


class Wi027Post(Model):
    __tablename__ = "wi027_posts"
    id: int = id_()
    title: str = string(120)

    comments: ClassVar[MorphMany[Wi027Comment]] = MorphMany(Wi027Comment, name="commentable")


class Wi027Video(Model):
    __tablename__ = "wi027_videos"
    id: int = id_()
    name: str = string(120)

    comments: ClassVar[MorphMany[Wi027Comment]] = MorphMany(Wi027Comment, name="commentable")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _SelectCounter:
    """Counts SELECT statements run on the engine, for N+1 assertions."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


class TestResolveParent:
    async def test_resolves_post_parent(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi027Post.create(title="Hello")
        comment = await Wi027Comment.create(
            body="nice", commentable_type="Wi027Post", commentable_id=post.id
        )
        parent = await comment.commentable
        assert isinstance(parent, Wi027Post)
        assert parent.id == post.id

    async def test_null_discriminators_return_none(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        comment = await Wi027Comment.create(body="orphan")
        assert (await comment.commentable) is None


class TestAssociateDissociate:
    async def test_associate_sets_both_columns(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        video = await Wi027Video.create(name="clip")
        comment = await Wi027Comment.create(body="hi")
        comment.commentable.associate(video)
        assert comment.commentable_type == "Wi027Video"
        assert comment.commentable_id == video.id
        # Cache primed by associate — no DB round-trip needed.
        assert (await comment.commentable) is video

    async def test_dissociate_clears_both(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi027Post.create(title="p")
        comment = await Wi027Comment.create(
            body="c", commentable_type="Wi027Post", commentable_id=post.id
        )
        comment.commentable.dissociate()
        assert comment.commentable_type is None
        assert comment.commentable_id is None
        assert (await comment.commentable) is None


class TestEagerBatching:
    async def test_one_query_per_distinct_type(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post_a = await Wi027Post.create(title="A")
        post_b = await Wi027Post.create(title="B")
        video = await Wi027Video.create(name="V")
        await Wi027Comment.create(body="a1", commentable_type="Wi027Post", commentable_id=post_a.id)
        await Wi027Comment.create(body="b1", commentable_type="Wi027Post", commentable_id=post_b.id)
        await Wi027Comment.create(body="v1", commentable_type="Wi027Video", commentable_id=video.id)

        from sqlalchemy import event

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            comments = await Wi027Comment.query().with_("commentable").get()
            # 1 query for comments + 1 per distinct parent type (Post, Video) = 3.
            assert counter.count == 3
            # Accessing the parent reads from cache — no further queries.
            before = counter.count
            parents = [await c.commentable for c in comments]
            assert counter.count == before
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)

        kinds = sorted(type(p).__name__ for p in parents if p is not None)
        assert kinds == ["Wi027Post", "Wi027Post", "Wi027Video"]
