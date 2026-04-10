"""Tests for polymorphic (morph) relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import String, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel
from arvel.data.relationships.morphs import (
    _MORPH_TYPE_MAP,
    load_morph_parent,
    morph_alias,
    morph_many,
    morph_to,
    query_morph_children,
    register_morph_type,
    resolve_morph_type,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# ──── Models ────


class MorphPost(ArvelModel):
    __tablename__ = "morph_posts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))


class MorphVideo(ArvelModel):
    __tablename__ = "morph_videos"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))


class MorphComment(ArvelModel):
    __tablename__ = "morph_comments"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(String(500))
    commentable_type: Mapped[str] = mapped_column(String(100))
    commentable_id: Mapped[int] = mapped_column()

    commentable = morph_to("commentable")


# ──── Fixtures ────


@pytest.fixture(scope="module", params=["asyncio"], autouse=True)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(autouse=True)
def _register_types():
    """Register morph types before each test, clean up after."""
    register_morph_type("post", MorphPost)
    register_morph_type("video", MorphVideo)
    yield
    _MORPH_TYPE_MAP.clear()


@pytest.fixture
async def morph_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(ArvelModel.metadata.create_all)

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
            if trans.is_active:
                await trans.rollback()

    await engine.dispose()


# ──── Type map tests ────


class TestMorphTypeMap:
    def test_register_and_resolve(self):
        assert resolve_morph_type("post") is MorphPost
        assert resolve_morph_type("video") is MorphVideo

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown morph type"):
            resolve_morph_type("nonexistent")

    def test_morph_alias(self):
        assert morph_alias(MorphPost) == "post"
        assert morph_alias(MorphVideo) == "video"

    def test_morph_alias_unregistered_falls_back_to_class_name(self):
        class Unregistered(ArvelModel):
            __tablename__ = "unregistered_morphs"
            __abstract__ = True

        assert morph_alias(Unregistered) == "Unregistered"


# ──── morph_to tests ────


class TestMorphTo:
    async def test_load_morph_parent_post(self, morph_session: AsyncSession) -> None:
        post = MorphPost(title="Hello World")
        morph_session.add(post)
        await morph_session.flush()

        comment = MorphComment(body="Great post!", commentable_type="post", commentable_id=post.id)
        morph_session.add(comment)
        await morph_session.flush()

        parent = await load_morph_parent(comment, "commentable", morph_session)
        assert parent is not None
        assert isinstance(parent, MorphPost)
        assert parent.id == post.id

    async def test_load_morph_parent_video(self, morph_session: AsyncSession) -> None:
        video = MorphVideo(title="Cool Video")
        morph_session.add(video)
        await morph_session.flush()

        comment = MorphComment(
            body="Nice video!", commentable_type="video", commentable_id=video.id
        )
        morph_session.add(comment)
        await morph_session.flush()

        parent = await load_morph_parent(comment, "commentable", morph_session)
        assert parent is not None
        assert isinstance(parent, MorphVideo)

    async def test_load_morph_parent_null_type(self, morph_session: AsyncSession) -> None:
        comment = MorphComment(body="Orphan", commentable_type="", commentable_id=0)
        morph_session.add(comment)
        await morph_session.flush()

        setattr(comment, "commentable_type", None)  # noqa: B010
        parent = await load_morph_parent(comment, "commentable", morph_session)
        assert parent is None

    async def test_load_morph_parent_unknown_type_raises(self, morph_session: AsyncSession) -> None:
        comment = MorphComment(body="Bad", commentable_type="unknown_thing", commentable_id=1)
        morph_session.add(comment)
        await morph_session.flush()

        with pytest.raises(ValueError, match="Unknown morph type"):
            await load_morph_parent(comment, "commentable", morph_session)


# ──── morph_many tests ────


class TestMorphMany:
    async def test_query_morph_children(self, morph_session: AsyncSession) -> None:
        post = MorphPost(title="Post 1")
        morph_session.add(post)
        await morph_session.flush()

        c1 = MorphComment(body="C1", commentable_type="post", commentable_id=post.id)
        c2 = MorphComment(body="C2", commentable_type="post", commentable_id=post.id)
        c3 = MorphComment(body="C3", commentable_type="video", commentable_id=999)
        morph_session.add_all([c1, c2, c3])
        await morph_session.flush()

        children = await query_morph_children(post, MorphComment, "commentable", morph_session)
        assert len(children) == 2
        assert all(isinstance(c, MorphComment) for c in children)
        assert all(c.commentable_type == "post" for c in children)

    async def test_query_morph_children_empty(self, morph_session: AsyncSession) -> None:
        video = MorphVideo(title="Empty Video")
        morph_session.add(video)
        await morph_session.flush()

        children = await query_morph_children(video, MorphComment, "commentable", morph_session)
        assert children == []

    async def test_query_morph_children_different_parents(
        self, morph_session: AsyncSession
    ) -> None:
        post = MorphPost(title="Post A")
        video = MorphVideo(title="Video B")
        morph_session.add_all([post, video])
        await morph_session.flush()

        c1 = MorphComment(body="For post", commentable_type="post", commentable_id=post.id)
        c2 = MorphComment(body="For video", commentable_type="video", commentable_id=video.id)
        morph_session.add_all([c1, c2])
        await morph_session.flush()

        post_comments = await query_morph_children(post, MorphComment, "commentable", morph_session)
        video_comments = await query_morph_children(
            video, MorphComment, "commentable", morph_session
        )

        assert len(post_comments) == 1
        assert post_comments[0].body == "For post"
        assert len(video_comments) == 1
        assert video_comments[0].body == "For video"


# ──── Descriptor tests ────


class TestDescriptors:
    def test_morph_to_descriptor(self):
        desc = morph_to("commentable")
        assert desc.morph_name == "commentable"
        assert desc.morph_type == "morph_to"

    def test_morph_many_descriptor(self):
        desc = morph_many(MorphComment, "commentable")
        assert desc.morph_name == "commentable"
        assert desc.morph_type == "morph_many"
        assert desc.related_model is MorphComment

    def test_morph_to_on_model_class(self):
        desc = MorphComment.__dict__["commentable"]
        assert hasattr(desc, "morph_name")
        assert desc.morph_name == "commentable"
