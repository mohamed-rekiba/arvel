"""Morph relations (MorphOne, MorphMany).

Single-instance access, short-name discriminators, collections,
and shared polymorphic tables. Reads go through strict eager loading
(``.with_("relation")``); writes go directly to the child model with
the discriminator columns set by the caller.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, Timestamps, column, id_, integer, string
from arvel.database.orm import MorphMany, MorphOne
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession

# ─── Schema ──────────────────────────────────────────────────────────────────


class MorphImage(Model, Timestamps):
    """Polymorphic image — can belong to MorphPost or MorphVideo."""

    __tablename__ = "morph_images"

    id: int = id_()
    url: str = string(2048)
    imageable_type: str = string(255)
    imageable_id: int = integer()


class MorphComment(Model, Timestamps):
    """Polymorphic comment — MorphMany example."""

    __tablename__ = "morph_comments"

    id: int = id_()
    body: str = string(1000)
    commentable_type: str = string(255)
    commentable_id: int = integer()


class MorphPost(Model, Timestamps):
    __tablename__ = "morph_posts"

    id: int = id_()
    title: str = string(200)

    image: ClassVar[MorphOne[MorphImage]] = MorphOne(MorphImage, name="imageable")
    comments: ClassVar[MorphMany[MorphComment]] = MorphMany(MorphComment, name="commentable")


class MorphVideo(Model, Timestamps):
    """Second owner type — shares morph_images with MorphPost."""

    __tablename__ = "morph_videos"

    id: int = id_()
    title: str = string(200)

    image: ClassVar[MorphOne[MorphImage]] = MorphOne(MorphImage, name="imageable")


class MorphArticle(Model, Timestamps):
    """Owner with a non-"id" string primary key — exercises mapper-based PK resolution."""

    __tablename__ = "morph_articles"

    slug: str = column(String(80), primary_key=True)
    title: str = string(200)

    comments: ClassVar[MorphMany[MorphComment]] = MorphMany(MorphComment, name="commentable")


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ───  MorphOne returns single instance or None ──────────────────


async def test_morph_one_returns_related_instance(engine: Any, session: AsyncSession) -> None:
    """MorphOne returns the related model instance after eager loading."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Hello")
    img = await MorphImage.create(
        url="https://example.com/img.jpg",
        imageable_type="MorphPost",
        imageable_id=post.id,
    )

    loaded = await MorphPost.with_("image").where(MorphPost.__table__.c.id == post.id).first()

    assert loaded is not None
    assert loaded.image is not None
    assert loaded.image.id == img.id
    assert loaded.image.url == img.url


async def test_morph_one_returns_none_when_no_related(engine: Any, session: AsyncSession) -> None:
    """MorphOne returns None when no related row exists."""
    await _create_tables(engine)
    post = await MorphPost.create(title="No Image")

    loaded = await MorphPost.with_("image").where(MorphPost.__table__.c.id == post.id).first()

    assert loaded is not None
    assert loaded.image is None


async def test_morph_one_returns_first_when_multiple_rows(
    engine: Any, session: AsyncSession
) -> None:
    """MorphOne must return the first match, not blow up, when duplicates exist."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Two Images")
    first = await MorphImage.create(
        url="https://example.com/a.jpg",
        imageable_type="MorphPost",
        imageable_id=post.id,
    )
    await MorphImage.create(
        url="https://example.com/b.jpg",
        imageable_type="MorphPost",
        imageable_id=post.id,
    )

    loaded = await MorphPost.with_("image").where(MorphPost.__table__.c.id == post.id).first()

    assert loaded is not None
    assert loaded.image is not None
    assert loaded.image.id == first.id


# ───  MorphMany yields all matching instances ──────────────────


async def test_morph_many_yields_all_related(engine: Any, session: AsyncSession) -> None:
    """MorphMany returns all related instances for this owner after eager loading."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Multi-Comment")
    other_post = await MorphPost.create(title="Other")

    await MorphComment.create(body="A", commentable_type="MorphPost", commentable_id=post.id)
    await MorphComment.create(body="B", commentable_type="MorphPost", commentable_id=post.id)
    await MorphComment.create(body="C", commentable_type="MorphPost", commentable_id=other_post.id)

    loaded = await MorphPost.with_("comments").where(MorphPost.__table__.c.id == post.id).first()

    assert loaded is not None
    assert len(loaded.comments) == 2
    assert all(c.commentable_id == post.id for c in loaded.comments)


async def test_morph_many_returns_empty_list_when_none(engine: Any, session: AsyncSession) -> None:
    """MorphMany returns [] when no related rows exist."""
    await _create_tables(engine)
    post = await MorphPost.create(title="No Comments")

    loaded = await MorphPost.with_("comments").where(MorphPost.__table__.c.id == post.id).first()

    assert loaded is not None
    assert loaded.comments == []


# ───  two owner types share the same polymorphic table ──────────


async def test_two_owners_share_polymorphic_table(engine: Any, session: AsyncSession) -> None:
    """MorphPost and MorphVideo each see only their own image."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Post with image")
    video = await MorphVideo.create(title="Video with image")

    post_img = await MorphImage.create(
        url="https://example.com/post.jpg", imageable_type="MorphPost", imageable_id=post.id
    )
    video_img = await MorphImage.create(
        url="https://example.com/video.jpg", imageable_type="MorphVideo", imageable_id=video.id
    )

    loaded_post = await MorphPost.with_("image").where(MorphPost.__table__.c.id == post.id).first()
    loaded_video = await (
        MorphVideo.with_("image").where(MorphVideo.__table__.c.id == video.id).first()
    )

    assert loaded_post is not None
    assert loaded_video is not None
    assert loaded_post.image is not None
    assert loaded_video.image is not None
    assert loaded_post.image.id == post_img.id
    assert loaded_video.image.id == video_img.id
    assert loaded_post.image.id != loaded_video.image.id


async def test_morph_many_resolves_non_id_primary_key(engine: Any, session: AsyncSession) -> None:
    """Owner PK is resolved via the mapper, so non-"id" PKs work end to end."""
    await _create_tables(engine)
    article = await MorphArticle.create(slug="intro", title="Intro")

    comment = await MorphComment.create(
        body="On a slug-keyed owner",
        commentable_type="MorphArticle",
        commentable_id=article.slug,
    )

    loaded = await (
        MorphArticle.query()
        .with_("comments")
        .where(MorphArticle.__table__.c.slug == "intro")
        .first()
    )
    assert loaded is not None
    assert [c.id for c in loaded.comments] == [comment.id]


async def test_polymorphic_images_are_isolated_by_owner_type(
    engine: Any, session: AsyncSession
) -> None:
    """MorphOne does not return images belonging to a different owner type."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Post")
    await MorphVideo.create(title="Video")

    # Same imageable_id as the post but different type — must not cross-pollinate.
    await MorphImage.create(
        url="https://example.com/video.jpg",
        imageable_type="MorphVideo",
        imageable_id=post.id,
    )

    loaded = await MorphPost.with_("image").where(MorphPost.__table__.c.id == post.id).first()

    assert loaded is not None
    assert loaded.image is None
