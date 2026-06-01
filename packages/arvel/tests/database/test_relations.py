"""HasMany, HasOne, and BelongsTo relation helpers."""

from __future__ import annotations

from typing import Any

from arvel.database import Model, foreign_id, id_, string
from sqlalchemy.ext.asyncio import AsyncSession


class RelUser(Model):
    __tablename__ = "rel_users"
    id: int = id_()
    name: str = string(80)

    def posts(self) -> Any:
        # FK inferred as rel_user_id (snake_case of RelUser + _id)
        return self.has_many(RelPost)

    def profile(self) -> Any:
        return self.has_one(RelProfile)


class RelPost(Model):
    __tablename__ = "rel_posts"
    id: int = id_()
    title: str = string(200)
    rel_user_id: int = foreign_id("rel_users.id")

    def author(self) -> Any:
        # FK inferred as rel_user_id (snake_case of RelUser + _id) on this model
        return self.belongs_to(RelUser)


class RelProfile(Model):
    __tablename__ = "rel_profiles"
    id: int = id_()
    bio: str = string(500)
    rel_user_id: int = foreign_id("rel_users.id")


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── has_many ────────────────────────────────────────────────────────────────


async def test_has_many_returns_query_builder(engine: Any, session: AsyncSession) -> None:
    """has_many(T) returns QueryBuilder[T] with FK WHERE."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    builder = user.posts()
    sql = builder.to_sql()
    assert "rel_posts" in sql.lower()
    assert "rel_user_id" in sql.lower()


async def test_has_many_fetches_related_records(engine: Any, session: AsyncSession) -> None:
    """has_many returns only records belonging to the owner."""
    await _create_tables(engine)
    alice = await RelUser.create(name="alice")
    bob = await RelUser.create(name="bob")
    await RelPost.create(title="alice-post-1", rel_user_id=alice.id)
    await RelPost.create(title="alice-post-2", rel_user_id=alice.id)
    await RelPost.create(title="bob-post", rel_user_id=bob.id)

    posts = await alice.posts().all()
    assert len(posts) == 2
    assert all(p.rel_user_id == alice.id for p in posts)


async def test_has_many_chains_where(engine: Any, session: AsyncSession) -> None:
    """has_many result supports further .where chaining."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    await RelPost.create(title="first", rel_user_id=user.id)
    await RelPost.create(title="second", rel_user_id=user.id)

    posts = await user.posts().where(RelPost.title == "first").all()
    assert len(posts) == 1
    assert posts[0].title == "first"


async def test_has_many_explicit_fk(engine: Any, session: AsyncSession) -> None:
    """has_many accepts explicit foreign_key override."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    builder = user.has_many(RelProfile, foreign_key="rel_user_id")
    sql = builder.to_sql()
    assert "rel_user_id" in sql.lower()


async def test_has_many_empty_when_no_related(engine: Any, session: AsyncSession) -> None:
    """has_many returns empty list when no related records exist."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    posts = await user.posts().all()
    assert posts == []


# ─── has_one ─────────────────────────────────────────────────────────────────


async def test_has_one_returns_single_record(engine: Any, session: AsyncSession) -> None:
    """has_one(T) returns the first matching record."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    await RelProfile.create(bio="hello", rel_user_id=user.id)

    profile = await user.has_one(RelProfile, foreign_key="rel_user_id").first()
    assert profile is not None
    assert profile.bio == "hello"


async def test_has_one_returns_none_when_no_related(engine: Any, session: AsyncSession) -> None:
    """has_one returns None when no related record exists."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    profile = await user.has_one(RelProfile, foreign_key="rel_user_id").first()
    assert profile is None


# ─── belongs_to ──────────────────────────────────────────────────────────────


async def test_belongs_to_fetches_owner(engine: Any, session: AsyncSession) -> None:
    """belongs_to(T) fetches the owning record."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    post = await RelPost.create(title="hello", rel_user_id=user.id)

    author = await post.author().first()
    assert author is not None
    assert author.id == user.id
    assert author.name == "alice"


async def test_belongs_to_sql_has_pk_where(engine: Any, session: AsyncSession) -> None:
    """belongs_to SQL contains WHERE id = <owner_pk>."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    post = await RelPost.create(title="hello", rel_user_id=user.id)

    sql = post.author().to_sql()
    assert "rel_users" in sql.lower()


async def test_belongs_to_returns_none_when_no_owner(engine: Any, session: AsyncSession) -> None:
    """belongs_to returns None when FK is null or owner was deleted."""
    await _create_tables(engine)
    user = await RelUser.create(name="alice")
    post = await RelPost.create(title="hello", rel_user_id=user.id)
    # Delete the user to simulate missing owner
    await user.delete()
    author = await post.author().first()
    assert author is None
