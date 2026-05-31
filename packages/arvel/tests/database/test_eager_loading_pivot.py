"""Batched eager-loading for MorphToMany / BelongsToMany via ``with_()``.

Eloquent parity: ``with_("tags")`` defers, then loads every parent's pivot
relation in a single ``WHERE pivot.owner_id IN (...)`` query (plus a
``morph_type`` filter for MorphToMany), so an N-row list never fans out into
N per-row lookups.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.database import Model, id_, string
from arvel.database.orm import BelongsToMany, MorphToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

el_taggables = Table(
    "el_taggables",
    Model.metadata,
    Column("tag_id", Integer, ForeignKey("el_tags.id"), primary_key=True),
    Column("taggable_type", String(255), primary_key=True),
    Column("taggable_id", String(64), primary_key=True),
)

el_post_topic = Table(
    "el_post_topic",
    Model.metadata,
    Column("post_id", Integer, ForeignKey("el_posts.id"), primary_key=True),
    Column("topic_id", Integer, ForeignKey("el_topics.id"), primary_key=True),
)


class ElTag(Model):
    __tablename__ = "el_tags"
    id: int = id_()
    name: str = string(80)


class ElTopic(Model):
    __tablename__ = "el_topics"
    id: int = id_()
    name: str = string(80)


class ElPost(Model):
    __tablename__ = "el_posts"
    id: int = id_()
    title: str = string(80)
    tags: ClassVar[MorphToMany[ElTag]] = MorphToMany(
        ElTag, table=el_taggables, name="taggable", related_key="tag_id"
    )
    topics: ClassVar[BelongsToMany[ElTopic]] = BelongsToMany(
        ElTopic, table=el_post_topic, foreign_key="post_id", related_foreign_key="topic_id"
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _PivotProbe:
    """Counts executed statements that touch a given table name."""

    def __init__(self, engine: AsyncEngine, table_name: str) -> None:
        self._table = table_name
        self.count = 0
        sync_engine = engine.sync_engine

        def _listen(
            conn: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if self._table in statement and statement.lstrip().upper().startswith("SELECT"):
                self.count += 1

        self._fn = _listen
        sa_event.listen(sync_engine, "before_cursor_execute", _listen)

    def remove(self, engine: AsyncEngine) -> None:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", self._fn)


class TestMorphToManyEagerLoad:
    async def test_with_loads_in_one_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await ElPost.create(title="p1")
        p2 = await ElPost.create(title="p2")
        await ElPost.create(title="p3")  # no tags
        red = await ElTag.create(name="red")
        blue = await ElTag.create(name="blue")
        await p1.tags.attach(red.id)
        await p1.tags.attach(blue.id)
        await p2.tags.attach(red.id)

        probe = _PivotProbe(engine, "el_taggables")
        try:
            posts = await ElPost.query().with_("tags").order_by("id").all()
            # Accessor reads must hit the cache — zero extra pivot SELECTs.
            loaded = {p.title: sorted(t.name for t in await p.tags.all()) for p in posts}
        finally:
            probe.remove(engine)

        assert loaded == {"p1": ["blue", "red"], "p2": ["red"], "p3": []}
        # One batched pivot query for all three posts — not one per post.
        assert probe.count == 1

    async def test_without_with_is_n_plus_one(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await ElPost.create(title="p1")
        p2 = await ElPost.create(title="p2")
        tag = await ElTag.create(name="t")
        await p1.tags.attach(tag.id)
        await p2.tags.attach(tag.id)

        probe = _PivotProbe(engine, "el_taggables")
        try:
            posts = await ElPost.query().order_by("id").all()
            for p in posts:
                await p.tags.all()
        finally:
            probe.remove(engine)

        # No eager load → one pivot SELECT per post (the N+1 we fixed).
        assert probe.count == 2

    async def test_attach_busts_cache(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await ElPost.create(title="p")
        red = await ElTag.create(name="red")
        blue = await ElTag.create(name="blue")
        await post.tags.attach(red.id)

        loaded = (await ElPost.query().with_("tags").all())[0]
        assert [t.name for t in await loaded.tags.all()] == ["red"]
        await loaded.tags.attach(blue.id)
        assert sorted(t.name for t in await loaded.tags.all()) == ["blue", "red"]

    async def test_detach_busts_cache(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await ElPost.create(title="p")
        red = await ElTag.create(name="red")
        blue = await ElTag.create(name="blue")
        await post.tags.attach(red.id)
        await post.tags.attach(blue.id)

        loaded = (await ElPost.query().with_("tags").all())[0]
        assert sorted(t.name for t in await loaded.tags.all()) == ["blue", "red"]
        await loaded.tags.detach(blue.id)
        assert [t.name for t in await loaded.tags.all()] == ["red"]

    async def test_constrained_with_filters_pivot_rows(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await ElPost.create(title="p")
        red = await ElTag.create(name="red")
        blue = await ElTag.create(name="blue")
        await post.tags.attach(red.id)
        await post.tags.attach(blue.id)

        loaded = (
            await ElPost.query().with_({"tags": lambda qb: qb.where(ElTag.name == "red")}).all()
        )[0]
        assert [t.name for t in await loaded.tags.all()] == ["red"]

    async def test_chunk_eager_loads_per_batch(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        for i in range(4):
            p = await ElPost.create(title=f"p{i}")
            tag = await ElTag.create(name=f"t{i}")
            await p.tags.attach(tag.id)

        seen: list[str] = []
        probe = _PivotProbe(engine, "el_taggables")
        try:

            async def _collect(batch: list[ElPost]) -> None:
                for post in batch:
                    seen.extend(t.name for t in await post.tags.all())

            await ElPost.query().with_("tags").order_by("id").chunk(2, _collect)
        finally:
            probe.remove(engine)

        assert sorted(seen) == ["t0", "t1", "t2", "t3"]
        # Two chunks → one batched pivot SELECT each, not one per row.
        assert probe.count == 2

    async def test_lazy_eager_loads_per_batch(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        for i in range(3):
            p = await ElPost.create(title=f"p{i}")
            tag = await ElTag.create(name=f"t{i}")
            await p.tags.attach(tag.id)

        seen: list[str] = []
        probe = _PivotProbe(engine, "el_taggables")
        try:
            async for post in ElPost.query().with_("tags").order_by("id").lazy(chunk_size=2):
                seen.extend(t.name for t in await post.tags.all())
        finally:
            probe.remove(engine)

        assert sorted(seen) == ["t0", "t1", "t2"]
        # chunk_size=2 over 3 rows → two batches, one pivot SELECT each.
        assert probe.count == 2


class TestBelongsToManyEagerLoad:
    async def test_with_loads_in_one_query(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await ElPost.create(title="p1")
        p2 = await ElPost.create(title="p2")
        await ElPost.create(title="p3")
        a = await ElTopic.create(name="a")
        b = await ElTopic.create(name="b")
        await p1.topics.attach(a.id)
        await p1.topics.attach(b.id)
        await p2.topics.attach(a.id)

        probe = _PivotProbe(engine, "el_post_topic")
        try:
            posts = await ElPost.query().with_("topics").order_by("id").all()
            loaded = {p.title: sorted(t.name for t in await p.topics.all()) for p in posts}
        finally:
            probe.remove(engine)

        assert loaded == {"p1": ["a", "b"], "p2": ["a"], "p3": []}
        assert probe.count == 1

    async def test_without_with_is_n_plus_one(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await ElPost.create(title="p1")
        p2 = await ElPost.create(title="p2")
        topic = await ElTopic.create(name="a")
        await p1.topics.attach(topic.id)
        await p2.topics.attach(topic.id)

        probe = _PivotProbe(engine, "el_post_topic")
        try:
            posts = await ElPost.query().order_by("id").all()
            for p in posts:
                await p.topics.all()
        finally:
            probe.remove(engine)

        assert probe.count == 2
