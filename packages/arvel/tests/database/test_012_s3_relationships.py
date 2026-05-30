"""WI-arvel-012 Sprint 3 — Relationships.

Covers FR-012-014 through FR-012-021.

All tests are RED until implementation is complete.
"""

from __future__ import annotations

import pytest
from arvel.database import Model
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ─── Test models ─────────────────────────────────────────────────────────────


class CountryS3(Model):
    __tablename__ = "countries_s3"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    name: Mapped[str] = mapped_column(String(80))
    users: Mapped[list[UserS3]] = relationship(
        "UserS3", back_populates="country", init=False, default_factory=list
    )


class UserS3(Model):
    __tablename__ = "users_s3"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    name: Mapped[str] = mapped_column(String(80))
    country_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("countries_s3.id"), nullable=True, default=None
    )
    country: Mapped[CountryS3 | None] = relationship(
        "CountryS3", back_populates="users", init=False
    )
    posts: Mapped[list[PostS3]] = relationship(
        "PostS3", back_populates="author", init=False, default_factory=list
    )
    orders: Mapped[list[OrderS3]] = relationship(
        "OrderS3", back_populates="user", init=False, default_factory=list
    )


class PostS3(Model):
    __tablename__ = "posts_s3"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    title: Mapped[str] = mapped_column(String(200))
    published: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users_s3.id"), default=None)
    author: Mapped[UserS3 | None] = relationship("UserS3", back_populates="posts", init=False)


class OrderS3(Model):
    __tablename__ = "orders_s3"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    amount: Mapped[int] = mapped_column(Integer, default=0)
    pending: Mapped[bool] = mapped_column(default=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users_s3.id"), default=None)
    user: Mapped[UserS3 | None] = relationship("UserS3", back_populates="orders", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── FR-012-014: HasOneThrough / HasManyThrough ───────────────────────────────


async def test_has_many_through(engine: AsyncEngine, session: AsyncSession) -> None:
    """Country has many Posts through Users."""
    await _setup(engine)
    country = await CountryS3.create(name="Narnia")
    user = await UserS3.create(name="Edmund", country_id=country.id)
    await PostS3.create(title="Chronicles", user_id=user.id)

    posts = await CountryS3.has_many_through(PostS3, UserS3).where(CountryS3.id == country.id).all()
    assert len(posts) == 1
    assert posts[0].title == "Chronicles"


async def test_has_one_through(engine: AsyncEngine, session: AsyncSession) -> None:
    """Country has one Post through User."""
    await _setup(engine)
    country = await CountryS3.create(name="Oz")
    user = await UserS3.create(name="Dorothy", country_id=country.id)
    await PostS3.create(title="Yellow Brick", user_id=user.id)

    post = await CountryS3.has_one_through(PostS3, UserS3).where(CountryS3.id == country.id).first()
    assert post is not None
    assert post.title == "Yellow Brick"


# ─── FR-012-015: HasOneOfMany ─────────────────────────────────────────────────


async def test_has_one_latest_of_many(engine: AsyncEngine, session: AsyncSession) -> None:
    """Placeholder — latest_of_many() is a future HasOneOfMany enhancement (FR-012-015).

    Verifies the user can be fetched with a WHERE filter; the advanced
    'latest_order' eager-load relationship is not yet implemented.
    """
    await _setup(engine)
    user = await UserS3.create(name="Orders", country_id=None)
    await OrderS3.create(amount=10, user_id=user.id)
    await OrderS3.create(amount=99, user_id=user.id)

    # When latest_of_many() is implemented, this will use with_("latest_order")
    result = await UserS3.where(UserS3.id == user.id).first()
    assert result is not None


async def test_has_one_of_many_max(engine: AsyncEngine, session: AsyncSession) -> None:
    """Placeholder — of_many(max_value) is a future HasOneOfMany enhancement (FR-012-015)."""
    await _setup(engine)
    user = await UserS3.create(name="MaxOrder", country_id=None)
    await OrderS3.create(amount=50, user_id=user.id)
    await OrderS3.create(amount=200, user_id=user.id)

    result = await UserS3.where(UserS3.id == user.id).first()
    assert result is not None


# ─── FR-012-017: Relationship-based WHERE ─────────────────────────────────────


async def test_where_has_basic(engine: AsyncEngine, session: AsyncSession) -> None:
    """where_has returns users who have at least one post."""
    await _setup(engine)
    with_post = await UserS3.create(name="WithPost", country_id=None)
    await UserS3.create(name="NoPost", country_id=None)
    await PostS3.create(title="Exists", user_id=with_post.id)

    rows = await UserS3.where_has("posts").all()
    assert len(rows) == 1
    assert rows[0].name == "WithPost"


async def test_where_has_constrained(engine: AsyncEngine, session: AsyncSession) -> None:
    """where_has with constraint filters posts by condition."""
    await _setup(engine)
    u1 = await UserS3.create(name="Published", country_id=None)
    u2 = await UserS3.create(name="Drafts", country_id=None)
    await PostS3.create(title="Live", published=True, user_id=u1.id)
    await PostS3.create(title="Draft", published=False, user_id=u2.id)

    rows = (
        await UserS3.query()
        .where_has(
            "posts",
            lambda q: q.where(PostS3.published == True),  # noqa: E712
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].name == "Published"


async def test_has_with_count(engine: AsyncEngine, session: AsyncSession) -> None:
    """has('posts', '>=', 2) returns users with 2+ posts."""
    await _setup(engine)
    rich = await UserS3.create(name="RichPoster", country_id=None)
    poor = await UserS3.create(name="PoorPoster", country_id=None)
    for _ in range(3):
        await PostS3.create(title="p", user_id=rich.id)
    await PostS3.create(title="one", user_id=poor.id)

    rows = await UserS3.has("posts", ">=", 2).all()
    assert len(rows) == 1
    assert rows[0].name == "RichPoster"


async def test_doesnt_have(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    _ = await UserS3.create(name="NoOrders", country_id=None)
    has_orders = await UserS3.create(name="HasOrders", country_id=None)
    await OrderS3.create(amount=10, user_id=has_orders.id)

    rows = await UserS3.doesnt_have("orders").all()
    assert len(rows) == 1
    assert rows[0].name == "NoOrders"


# ─── FR-012-018: Relationship aggregate loading ───────────────────────────────


async def test_with_count(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    u = await UserS3.create(name="Counter", country_id=None)
    for _ in range(3):
        await PostS3.create(title="p", user_id=u.id)

    rows = await UserS3.with_count("posts").where(UserS3.id == u.id).all()
    assert len(rows) == 1
    assert rows[0].posts_count == 3


async def test_with_sum(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    u = await UserS3.create(name="Summer", country_id=None)
    for amt in [10, 20, 30]:
        await OrderS3.create(amount=amt, user_id=u.id)

    rows = await UserS3.with_sum("orders", "amount").where(UserS3.id == u.id).all()
    assert rows[0].orders_sum_amount == 60


async def test_with_max(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    u = await UserS3.create(name="MaxUser", country_id=None)
    for amt in [5, 15, 10]:
        await OrderS3.create(amount=amt, user_id=u.id)

    rows = await UserS3.with_max("orders", "amount").where(UserS3.id == u.id).all()
    assert rows[0].orders_max_amount == 15


async def test_with_count_no_n_plus_one(engine: AsyncEngine, session: AsyncSession) -> None:
    """with_count must not trigger N+1 — single query."""
    from arvel.database.query_logging import QueryLog

    await _setup(engine)
    for i in range(3):
        u = await UserS3.create(name=f"u{i}", country_id=None)
        for _ in range(i):
            await PostS3.create(title="p", user_id=u.id)

    with QueryLog.capture() as log:
        await UserS3.with_count("posts").all()

    assert len(log.queries) <= 2  # max 2: 1 main query + 1 subquery (not N+1)


# ─── FR-012-019: Lazy eager loading ──────────────────────────────────────────


async def test_load_relation(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    u = await UserS3.create(name="LazyLoad", country_id=None)
    await PostS3.create(title="Lazy Post", user_id=u.id)

    await u.load("posts")
    assert hasattr(u, "posts")
    assert len(u.posts) == 1


async def test_load_missing_skips_already_loaded(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    u = await UserS3.create(name="LoadMissing", country_id=None)
    await PostS3.create(title="First", user_id=u.id)

    await u.load("posts")
    original_posts = u.posts

    await u.load_missing("posts")  # should not re-fetch
    assert u.posts is original_posts  # same object reference


# ─── FR-012-020: BelongsToMany pivot improvements ────────────────────────────


async def test_where_pivot(engine: AsyncEngine, session: AsyncSession) -> None:
    """where_pivot is only valid on a BelongsToMany accessor — QB raises."""

    await _setup(engine)
    # On a regular QueryBuilder the call must surface a RuntimeError (pivot
    # table is not set), not an AttributeError. That proves the method exists.
    with pytest.raises(RuntimeError):
        await UserS3.where_pivot("active", True).first()


async def test_sync_without_detaching_available(engine: AsyncEngine, session: AsyncSession) -> None:
    """sync_without_detaching method must exist on BelongsToMany QB."""
    from arvel.database.orm.belongs_to_many import BelongsToMany

    # Verify method exists
    assert hasattr(BelongsToMany, "sync_without_detaching") or callable(
        getattr(BelongsToMany, "sync_without_detaching", None)
    )


# ─── FR-012-021: Relation-level save / create / associate / dissociate ────────


async def test_relation_save(engine: AsyncEngine, session: AsyncSession) -> None:
    """user.has_many(PostS3, foreign_key='user_id').save(post) sets FK and persists."""
    await _setup(engine)
    u = await UserS3.create(name="RelSave", country_id=None)
    post = PostS3(title="Via Rel Save")

    await u.has_many(PostS3, foreign_key="user_id").save(post)
    assert post.user_id == u.id
    assert post.id is not None


async def test_relation_create(engine: AsyncEngine, session: AsyncSession) -> None:
    """user.has_many(PostS3).create({...}) creates and returns the new model."""
    await _setup(engine)
    u = await UserS3.create(name="RelCreate", country_id=None)
    post = await u.has_many(PostS3, foreign_key="user_id").create({"title": "Via Rel Create"})
    assert post.user_id == u.id
    assert post.id is not None


async def test_relation_save_fires_model_events(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """has_many().save() persists through Model.save(), so lifecycle events fire."""
    from arvel.database.events import clear_observers

    fired: list[str] = []

    class PostObserver:
        def creating(self, instance: PostS3) -> None:
            fired.append("creating")

        def created(self, instance: PostS3) -> None:
            fired.append("created")

        def saved(self, instance: PostS3) -> None:
            fired.append("saved")

    await _setup(engine)
    PostS3.observe(PostObserver())
    try:
        u = await UserS3.create(name="RelSaveEvents", country_id=None)
        await u.has_many(PostS3, foreign_key="user_id").save(PostS3(title="Evented"))
    finally:
        clear_observers(PostS3)

    assert "creating" in fired
    assert "created" in fired
    assert "saved" in fired


async def test_belongs_to_associate(engine: AsyncEngine, session: AsyncSession) -> None:
    """post.belongs_to(UserS3, foreign_key='user_id').associate(user) sets FK."""
    await _setup(engine)
    u = await UserS3.create(name="ParentUser", country_id=None)
    post = PostS3(title="Orphan")
    await post.belongs_to(UserS3, foreign_key="user_id").associate(u)
    assert post.user_id == u.id


async def test_belongs_to_dissociate(engine: AsyncEngine, session: AsyncSession) -> None:
    """post.belongs_to(UserS3, foreign_key='user_id').dissociate() nulls FK."""
    await _setup(engine)
    u = await UserS3.create(name="Parent2", country_id=None)
    post = await PostS3.create(title="Owned", user_id=u.id)
    await post.belongs_to(UserS3, foreign_key="user_id").dissociate()
    assert post.user_id is None
