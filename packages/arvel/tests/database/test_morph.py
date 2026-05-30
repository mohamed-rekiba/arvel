"""S-005-11 — Morph relations (MorphOne, MorphMany).

AC covered:
  AC-005-018-01  MorphOne accessor returns a single related instance (or None)
  AC-005-018-02  MorphOne discriminator columns use short class name (ADR-022)
  AC-005-019-01  MorphMany accessor yields all matching related instances
  AC-005-020-01  creating via morph accessor sets discriminator columns correctly
  AC-005-021-01  two different owner types can share the same polymorphic table
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, Timestamps

# RED: arvel.database.orm.MorphOne / MorphMany do not exist yet
from arvel.database.orm import MorphMany, MorphOne
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# ─── Schema ──────────────────────────────────────────────────────────────────


class MorphImage(Model, Timestamps):
    """Polymorphic image — can belong to MorphPost or MorphVideo."""

    __tablename__ = "morph_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # discriminator columns — set by the descriptor, never manually
    imageable_type: Mapped[str] = mapped_column(String(255), nullable=False)
    imageable_id: Mapped[int] = mapped_column(Integer, nullable=False)


class MorphComment(Model, Timestamps):
    """Polymorphic comment — MorphMany example."""

    __tablename__ = "morph_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    commentable_type: Mapped[str] = mapped_column(String(255), nullable=False)
    commentable_id: Mapped[int] = mapped_column(Integer, nullable=False)


class MorphPost(Model, Timestamps):
    __tablename__ = "morph_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    image: ClassVar[MorphOne[MorphImage]] = MorphOne(MorphImage, name="imageable")
    comments: ClassVar[MorphMany[MorphComment]] = MorphMany(MorphComment, name="commentable")


class MorphVideo(Model, Timestamps):
    """Second owner type — shares morph_images with MorphPost."""

    __tablename__ = "morph_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    image: ClassVar[MorphOne[MorphImage]] = MorphOne(MorphImage, name="imageable")


class MorphArticle(Model, Timestamps):
    """Owner with a non-"id" string primary key — exercises mapper-based PK resolution."""

    __tablename__ = "morph_articles"

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    comments: ClassVar[MorphMany[MorphComment]] = MorphMany(MorphComment, name="commentable")


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── AC-005-018-01: MorphOne returns single instance or None ──────────────────


async def test_morph_one_returns_related_instance(engine: Any, session: AsyncSession) -> None:
    """AC-005-018-01: MorphOne returns the related model instance."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Hello")
    img = await MorphImage.create(
        url="https://example.com/img.jpg",
        imageable_type="MorphPost",
        imageable_id=post.id,
    )

    result = await post.image

    assert result is not None
    assert result.id == img.id
    assert result.url == img.url


async def test_morph_one_returns_none_when_no_related(engine: Any, session: AsyncSession) -> None:
    """AC-005-018-01: MorphOne returns None when no related row exists."""
    await _create_tables(engine)
    post = await MorphPost.create(title="No Image")

    result = await post.image

    assert result is None


# ─── AC-005-018-02: discriminator uses short class name ──────────────────────


async def test_morph_one_create_sets_short_class_name_discriminator(
    engine: Any, session: AsyncSession
) -> None:
    """AC-005-018-02: creating via MorphOne sets {name}_type to 'MorphPost' (not FQCN)."""
    await _create_tables(engine)
    post = await MorphPost.create(title="ADR-022 Post")

    img = await post.image.create(url="https://example.com/photo.jpg")

    # Reload from DB to verify stored discriminator value
    from sqlalchemy import select

    stmt = select(MorphImage).where(MorphImage.id == img.id)
    row = (await session.execute(stmt)).scalar_one()
    assert row.imageable_type == "MorphPost"  # short name, NOT fully-qualified
    assert row.imageable_id == post.id


async def test_morph_many_create_sets_short_class_name_discriminator(
    engine: Any, session: AsyncSession
) -> None:
    """AC-005-018-02: creating via MorphMany sets {name}_type to 'MorphPost'."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Comment Post")

    comment = await post.comments.create(body="Great post!")

    from sqlalchemy import select

    stmt = select(MorphComment).where(MorphComment.id == comment.id)
    row = (await session.execute(stmt)).scalar_one()
    assert row.commentable_type == "MorphPost"
    assert row.commentable_id == post.id


# ─── AC-005-019-01: MorphMany yields all matching instances ──────────────────


async def test_morph_many_yields_all_related(engine: Any, session: AsyncSession) -> None:
    """AC-005-019-01: MorphMany returns all related instances for this owner."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Multi-Comment")
    other_post = await MorphPost.create(title="Other")

    await MorphComment.create(
        body="Comment A", commentable_type="MorphPost", commentable_id=post.id
    )
    await MorphComment.create(
        body="Comment B", commentable_type="MorphPost", commentable_id=post.id
    )
    await MorphComment.create(
        body="Comment C", commentable_type="MorphPost", commentable_id=other_post.id
    )

    comments = await post.comments.all()

    assert len(comments) == 2
    assert all(c.commentable_id == post.id for c in comments)


async def test_morph_many_returns_empty_list_when_none(engine: Any, session: AsyncSession) -> None:
    """AC-005-019-01: MorphMany returns [] when no related rows exist."""
    await _create_tables(engine)
    post = await MorphPost.create(title="No Comments")

    comments = await post.comments.all()

    assert comments == []


# ─── AC-005-020-01: creating via morph accessor sets discriminator correctly ──


async def test_morph_one_create_via_accessor(engine: Any, session: AsyncSession) -> None:
    """AC-005-020-01: post.image.create() creates a row with correct discriminator."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Accessor Post")

    img = await post.image.create(url="https://cdn.example.com/banner.png")

    assert img.id is not None
    assert img.imageable_type == "MorphPost"
    assert img.imageable_id == post.id


# ─── AC-005-021-01: two owner types share the same polymorphic table ──────────


async def test_two_owners_share_polymorphic_table(engine: Any, session: AsyncSession) -> None:
    """AC-005-021-01: MorphPost and MorphVideo each have their own image row."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Post with image")
    video = await MorphVideo.create(title="Video with image")

    post_img = await post.image.create(url="https://example.com/post.jpg")
    video_img = await video.image.create(url="https://example.com/video.jpg")

    # Each owner sees only its own image
    post_result = await post.image
    video_result = await video.image

    assert post_result is not None
    assert video_result is not None
    assert post_result.id == post_img.id
    assert video_result.id == video_img.id
    assert post_result.id != video_result.id


async def test_morph_many_resolves_non_id_primary_key(engine: Any, session: AsyncSession) -> None:
    """Owner PK is resolved via the mapper, so non-"id" PKs work end to end."""
    await _create_tables(engine)
    article = await MorphArticle.create(slug="intro", title="Intro")

    comment = await article.comments.create(body="On a slug-keyed owner")

    assert comment.commentable_type == "MorphArticle"
    assert comment.commentable_id == "intro"  # the slug, not a missing .id
    fetched = await article.comments.all()
    assert [c.id for c in fetched] == [comment.id]


async def test_polymorphic_images_are_isolated_by_owner_type(
    engine: Any, session: AsyncSession
) -> None:
    """AC-005-021-01: MorphOne does not return images belonging to a different owner type."""
    await _create_tables(engine)
    post = await MorphPost.create(title="Post")
    await MorphVideo.create(title="Video")

    # Create an image for the video with the same imageable_id as the post
    # (edge case: both have id=1 — should not cross-pollinate)
    await MorphImage.create(
        url="https://example.com/video.jpg",
        imageable_type="MorphVideo",
        imageable_id=post.id,  # same id, different type
    )

    post_img = await post.image

    # Post has no image of type MorphPost → should be None
    assert post_img is None
