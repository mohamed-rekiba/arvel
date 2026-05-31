"""WI-arvel-029 — Epic 007 Story 4: morphedByMany (inverse morph pivot).

`MorphedByMany` is the inverse of `MorphToMany`: declared on the model the pivot's
`{name}_type`/`{name}_id` point at, with a plain owner FK column holding this owner's PK.
Mirrors Laravel's `morphedByMany` — e.g. `tag.posts` / `tag.videos` over one `taggables` pivot.

Covers: attach/detach/toggle/sync from the inverse side, discriminator isolation between
related types, batched eager loading (`with_`), `where_has`, and `with_count`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model
from arvel.database.orm import MorphedByMany, MorphToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

wi029_taggables = Table(
    "wi029_taggables",
    Model.metadata,
    Column("tag_id", Integer, ForeignKey("wi029_tags.id"), primary_key=True),
    Column("taggable_type", String(255), primary_key=True),
    Column("taggable_id", String(64), primary_key=True),
)


class Wi029Tag(Model):
    __tablename__ = "wi029_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))

    posts: ClassVar[MorphedByMany[Wi029Post]] = MorphedByMany(
        lambda: Wi029Post, table=wi029_taggables, name="taggable", related_key="tag_id"
    )
    videos: ClassVar[MorphedByMany[Wi029Video]] = MorphedByMany(
        lambda: Wi029Video, table=wi029_taggables, name="taggable", related_key="tag_id"
    )


class Wi029Post(Model):
    __tablename__ = "wi029_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80))

    tags: ClassVar[MorphToMany[Wi029Tag]] = MorphToMany(
        Wi029Tag, table=wi029_taggables, name="taggable", related_key="tag_id"
    )


class Wi029Video(Model):
    __tablename__ = "wi029_videos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80))

    tags: ClassVar[MorphToMany[Wi029Tag]] = MorphToMany(
        Wi029Tag, table=wi029_taggables, name="taggable", related_key="tag_id"
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


class TestInverseAccessor:
    async def test_attach_and_read_from_inverse(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tag = await Wi029Tag.create(name="python")
        post = await Wi029Post.create(title="hello")
        # attach from the forward (post) side, read from the inverse (tag) side.
        await post.tags.attach(tag.id)
        titles = [p.title for p in await tag.posts.all()]
        assert titles == ["hello"]

    async def test_inverse_attach_detach(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        tag = await Wi029Tag.create(name="rust")
        p1 = await Wi029Post.create(title="a")
        p2 = await Wi029Post.create(title="b")
        assert await tag.posts.attach(p1.id) is True
        assert await tag.posts.attach(p1.id) is False  # idempotent
        await tag.posts.attach(p2.id)
        assert sorted(p.title for p in await tag.posts.all()) == ["a", "b"]

        await tag.posts.detach(p1.id)
        assert [p.title for p in await tag.posts.all()] == ["b"]

    async def test_discriminator_isolates_related_types(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tag = await Wi029Tag.create(name="shared")
        post = await Wi029Post.create(title="p")
        video = await Wi029Video.create(title="v")
        await tag.posts.attach(post.id)
        await tag.videos.attach(video.id)

        assert [p.title for p in await tag.posts.all()] == ["p"]
        assert [v.title for v in await tag.videos.all()] == ["v"]

    async def test_toggle_and_sync(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        tag = await Wi029Tag.create(name="t")
        p1 = await Wi029Post.create(title="1")
        p2 = await Wi029Post.create(title="2")
        p3 = await Wi029Post.create(title="3")

        assert await tag.posts.toggle(p1.id) == "attached"
        assert await tag.posts.toggle(p1.id) == "detached"

        result = await tag.posts.sync([p1.id, p2.id])
        assert sorted(result["attached"]) == sorted([p1.id, p2.id])
        result = await tag.posts.sync([p2.id, p3.id])
        assert result["attached"] == [p3.id]
        assert result["detached"] == [p1.id]
        assert sorted(p.title for p in await tag.posts.all()) == ["2", "3"]


class TestInverseEager:
    async def test_with_batches_in_one_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        t1 = await Wi029Tag.create(name="t1")
        t2 = await Wi029Tag.create(name="t2")
        pa = await Wi029Post.create(title="a")
        pb = await Wi029Post.create(title="b")
        pc = await Wi029Post.create(title="c")
        await t1.posts.attach(pa.id)
        await t1.posts.attach(pb.id)
        await t2.posts.attach(pc.id)

        from sqlalchemy import event

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            tags = await Wi029Tag.query().with_("posts").get()
            assert counter.count == 2  # 1 for tags + 1 batched for posts
            before = counter.count
            grouped = {t.name: sorted(p.title for p in await t.posts.all()) for t in tags}
            assert counter.count == before  # served from cache
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)
        assert grouped == {"t1": ["a", "b"], "t2": ["c"]}


class TestInverseRelationQueries:
    async def test_where_has(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        t1 = await Wi029Tag.create(name="has")
        await Wi029Tag.create(name="none")
        post = await Wi029Post.create(title="p")
        await t1.posts.attach(post.id)

        names = [t.name for t in await Wi029Tag.query().where_has("posts").get()]
        assert names == ["has"]

    async def test_with_count(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        tag = await Wi029Tag.create(name="counted")
        p1 = await Wi029Post.create(title="a")
        p2 = await Wi029Post.create(title="b")
        await tag.posts.attach(p1.id)
        await tag.posts.attach(p2.id)

        tags = await Wi029Tag.query().with_count("posts").where(Wi029Tag.id == tag.id).get()
        assert tags[0].posts_count == 2
