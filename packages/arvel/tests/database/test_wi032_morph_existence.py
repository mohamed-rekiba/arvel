"""Polymorphic existence queries.

`where_has_morph` / `has_morph` / `where_morph_relation` filter a MorphTo across several
target types, building a union of per-type EXISTS/COUNT subqueries that honour the morph map."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from arvel.database import Model, id_, integer, string
from arvel.database.exceptions import UnknownRelationError
from arvel.database.orm import MorphTo
from arvel.database.orm.morph_map import get_morph_alias, morph_map, reset_morph_map
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi032Post(Model):
    __tablename__ = "wi032_posts"
    id: int = id_()
    title: str = string(120)


class Wi032Video(Model):
    __tablename__ = "wi032_videos"
    id: int = id_()
    name: str = string(120)


class Wi032Comment(Model):
    __tablename__ = "wi032_comments"
    id: int = id_()
    body: str = string(200)
    commentable_type: str | None = string(60, nullable=True, default=None)
    commentable_id: int | None = integer(nullable=True, default=None)

    commentable: ClassVar[MorphTo[Any]] = MorphTo(name="commentable")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def _comment_on(body: str, parent: Model) -> Wi032Comment:
    comment: Wi032Comment = await Wi032Comment.create(
        body=body,
        commentable_type=get_morph_alias(type(parent)),
        commentable_id=parent.get_key(),
    )
    return comment


@pytest.fixture(autouse=True)
def clean_morph_map() -> Iterator[None]:
    reset_morph_map()
    yield
    reset_morph_map()


class TestWhereHasMorph:
    async def test_filters_to_rows_pointing_at_given_types(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi032Post.create(title="p")
        video = await Wi032Video.create(name="v")
        await _comment_on("on-post", post)
        await _comment_on("on-video", video)

        rows = await Wi032Comment.query().where_has_morph("commentable", [Wi032Post]).get()
        assert {r.body for r in rows} == {"on-post"}

        both = (
            await Wi032Comment.query().where_has_morph("commentable", [Wi032Post, Wi032Video]).get()
        )
        assert {r.body for r in both} == {"on-post", "on-video"}

    async def test_per_type_constraint_receives_type(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        keep = await Wi032Post.create(title="keep")
        drop = await Wi032Post.create(title="drop")
        await _comment_on("a", keep)
        await _comment_on("b", drop)

        rows = (
            await Wi032Comment.query()
            .where_has_morph(
                "commentable",
                [Wi032Post],
                lambda q, _t: q.where(Wi032Post.__table__.c.title == "keep"),
            )
            .get()
        )
        assert {r.body for r in rows} == {"a"}

    async def test_honours_registered_morph_aliases(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        morph_map({"post": Wi032Post, "video": Wi032Video})
        post = await Wi032Post.create(title="aliased")
        c = await _comment_on("aliased-comment", post)
        assert c.commentable_type == "post"

        rows = await Wi032Comment.query().where_has_morph("commentable", [Wi032Post]).get()
        assert {r.body for r in rows} == {"aliased-comment"}

    async def test_empty_types_matches_nothing(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi032Post.create(title="p")
        await _comment_on("c", post)

        rows = await Wi032Comment.query().where_has_morph("commentable", []).get()
        assert rows == []

    async def test_non_morph_relation_raises(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        with pytest.raises(UnknownRelationError):
            Wi032Comment.query().where_has_morph("body", [Wi032Post])


class TestHasMorph:
    async def test_count_operator(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        post = await Wi032Post.create(title="p")
        video = await Wi032Video.create(name="v")
        await _comment_on("x", post)
        await _comment_on("y", video)

        # Each comment morphs to exactly one parent → has_morph >= 1 matches both types.
        rows = (
            await Wi032Comment.query()
            .has_morph("commentable", [Wi032Post, Wi032Video], ">=", 1)
            .get()
        )
        assert {r.body for r in rows} == {"x", "y"}

        only_posts = await Wi032Comment.query().has_morph("commentable", [Wi032Post], ">=", 1).get()
        assert {r.body for r in only_posts} == {"x"}


class TestWhereMorphRelation:
    async def test_filters_by_parent_column(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        keep = await Wi032Post.create(title="keep")
        drop = await Wi032Post.create(title="drop")
        await _comment_on("k", keep)
        await _comment_on("d", drop)

        rows = (
            await Wi032Comment.query()
            .where_morph_relation("commentable", [Wi032Post], "title", "keep")
            .get()
        )
        assert {r.body for r in rows} == {"k"}
