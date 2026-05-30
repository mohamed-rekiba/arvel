"""MorphToMany — polymorphic many-to-many over a typed pivot table.

The pivot carries ``{name}_type`` / ``{name}_id`` so one table links several
owner types to the same related model. The owner id is string-cast on write so
a VARCHAR pivot column accepts integer PKs.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from arvel.database import Model, Timestamps
from arvel.database.exceptions import UnknownRelationError
from arvel.database.orm import MorphToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

mtm_taggables = Table(
    "mtm_taggables",
    Model.metadata,
    Column("tag_id", Integer, ForeignKey("mtm_tags.id"), primary_key=True),
    Column("taggable_type", String(255), primary_key=True),
    Column("taggable_id", String(64), primary_key=True),
)


class MtmTag(Model, Timestamps):
    __tablename__ = "mtm_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))


class MtmPost(Model):
    __tablename__ = "mtm_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80))
    tags: ClassVar[MorphToMany[MtmTag]] = MorphToMany(
        MtmTag, table=mtm_taggables, name="taggable", related_key="tag_id"
    )


class MtmVideo(Model):
    __tablename__ = "mtm_videos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80))
    tags: ClassVar[MorphToMany[MtmTag]] = MorphToMany(
        MtmTag, table=mtm_taggables, name="taggable", related_key="tag_id"
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestMorphToManyAccessor:
    async def test_attach_and_all(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await MtmPost.create(title="hello")
        red = await MtmTag.create(name="red")
        blue = await MtmTag.create(name="blue")
        assert await post.tags.attach(red.id) is True
        assert await post.tags.attach(red.id) is False  # idempotent
        await post.tags.attach(blue.id)

        names = sorted(t.name for t in await post.tags.all())
        assert names == ["blue", "red"]

    async def test_discriminator_isolates_owner_types(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await MtmPost.create(title="p")
        video = await MtmVideo.create(title="v")
        tag = await MtmTag.create(name="shared")
        # Same numeric owner id space, different discriminator type.
        await post.tags.attach(tag.id)

        assert [t.name for t in await post.tags.all()] == ["shared"]
        assert await video.tags.all() == []

    async def test_detach_and_toggle(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await MtmPost.create(title="t")
        tag = await MtmTag.create(name="x")
        await post.tags.attach(tag.id)
        await post.tags.detach(tag.id)
        assert await post.tags.all() == []

        assert await post.tags.toggle(tag.id) == "attached"
        assert await post.tags.toggle(tag.id) == "detached"

    async def test_sync(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await MtmPost.create(title="s")
        a = await MtmTag.create(name="a")
        b = await MtmTag.create(name="b")
        c = await MtmTag.create(name="c")
        await post.tags.attach(a.id)
        result = await post.tags.sync([b.id, c.id])
        assert set(result["attached"]) == {b.id, c.id}
        assert result["detached"] == [a.id]
        assert sorted(t.name for t in await post.tags.all()) == ["b", "c"]

    async def test_survives_fresh_load(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await MtmPost.create(title="persist")
        tag = await MtmTag.create(name="keep")
        await post.tags.attach(tag.id)

        reloaded = await MtmPost.find_or_fail(post.id)
        assert [t.name for t in await reloaded.tags.all()] == ["keep"]


class TestMorphToManyExistence:
    async def test_where_has_and_with_count(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        tagged = await MtmPost.create(title="tagged")
        await MtmPost.create(title="bare")
        tag = await MtmTag.create(name="t")
        await tagged.tags.attach(tag.id)

        rows = await MtmPost.where_has("tags").all()
        assert [r.title for r in rows] == ["tagged"]

        counted: list[Any] = await MtmPost.query().with_count("tags").order_by("id").all()
        by_title = {r.title: r.tags_count for r in counted}
        assert by_title == {"tagged": 1, "bare": 0}

    async def test_with_count_unknown_relation(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        with pytest.raises(UnknownRelationError):
            await MtmPost.query().with_count("nope").all()
