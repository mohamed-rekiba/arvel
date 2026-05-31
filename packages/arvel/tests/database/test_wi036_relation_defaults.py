"""WI-arvel-036 — Epic 007 Story 11: relation defaults, eager control, cascade save.

Covers BelongsTo.with_default, QueryBuilder.without/with_only, Model.push, and $touches.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from arvel.database import Model
from arvel.database.orm.relations import BelongsTo
from sqlalchemy import DateTime, ForeignKey, Integer, String, event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Wi036User(Model):
    __tablename__ = "wi036_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), default="")
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    posts: Mapped[list[Wi036Post]] = relationship(
        "Wi036Post", back_populates="author", init=False, default_factory=list
    )


class Wi036Post(Model):
    __tablename__ = "wi036_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), default="")
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wi036_users.id"), nullable=True, default=None
    )
    author: Mapped[Wi036User | None] = relationship("Wi036User", back_populates="posts", init=False)

    __touches__: ClassVar[tuple[str, ...]] = ("author_relation",)

    def author_relation(self) -> BelongsTo[Wi036User]:
        return self.belongs_to(Wi036User, foreign_key="user_id")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


class TestWithDefault:
    async def test_returns_empty_default_when_fk_null(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi036Post.create(title="orphan")
        author = await post.author_relation().with_default().first()
        assert author is not None
        assert isinstance(author, Wi036User)
        assert author.id is None

    async def test_returns_default_with_attributes(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi036Post.create(title="orphan")
        author = await post.author_relation().with_default({"name": "Guest"}).first()
        assert author is not None
        assert author.name == "Guest"

    async def test_default_callback_receives_owner(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi036Post.create(title="orphan")

        def fill(instance: Wi036User, owner: Any) -> None:
            instance.name = f"author-of-{owner.title}"

        author = await post.author_relation().with_default(fill).first()
        assert author is not None
        assert author.name == "author-of-orphan"

    async def test_real_parent_wins_over_default(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="real")
        post = await Wi036Post.create(title="p", user_id=user.id)
        author = await post.author_relation().with_default({"name": "Guest"}).first()
        assert author is not None
        assert author.id == user.id
        assert author.name == "real"

    async def test_no_default_returns_none(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi036Post.create(title="orphan")
        assert await post.author_relation().first() is None


class TestEagerControl:
    async def test_without_drops_eager_load(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        await Wi036Post.create(title="a", user_id=user.id)

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            await Wi036User.query().with_("posts").without("posts").get()
            assert counter.count == 1  # only the users query, no selectin for posts
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)

    async def test_with_only_replaces_eager_loads(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        await Wi036Post.create(title="a", user_id=user.id)

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            await Wi036User.query().with_("posts").with_only("posts").get()
            assert counter.count == 2  # users + posts selectin (single load, not doubled)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)

    async def test_with_still_eager_loads(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        await Wi036Post.create(title="a", user_id=user.id)
        session.expire_all()

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            users = await Wi036User.query().with_("posts").get()
            assert counter.count == 2
            before = counter.count
            _ = [p.title for p in users[0].posts]
            assert counter.count == before  # served from cache
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)


class TestPush:
    async def test_push_cascades_to_loaded_relations(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        await Wi036Post.create(title="a", user_id=user.id)
        session.expire_all()

        loaded = await Wi036User.query().with_("posts").first()
        assert loaded is not None
        loaded.name = "renamed"
        loaded.posts[0].title = "edited"
        await loaded.push()

        await loaded.refresh()
        assert loaded.name == "renamed"
        fresh_post = await Wi036Post.query().where(Wi036Post.user_id == user.id).first()
        assert fresh_post is not None and fresh_post.title == "edited"

    async def test_push_skips_unloaded_relations(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        user_id = user.id
        await Wi036Post.create(title="a", user_id=user_id)
        session.expire_all()

        # No with_("posts") — the relation is unloaded; push must not touch it.
        loaded = await Wi036User.find(user_id)
        loaded.name = "renamed"
        await loaded.push()

        await loaded.refresh()
        assert loaded.name == "renamed"

    async def test_push_terminates_on_cyclic_loaded_graph(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        await Wi036Post.create(title="a", user_id=user.id)
        session.expire_all()

        loaded = await Wi036User.query().with_("posts").first()
        assert loaded is not None
        # Wire the inverse so user.posts[0].author is the same loaded user — a cycle.
        loaded.posts[0].author = loaded
        await loaded.push()  # must not recurse forever

        await loaded.refresh()
        assert loaded.name == "u"


class TestTouches:
    async def test_saving_child_touches_parent(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi036User.create(name="u")
        user.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        await user.save_quietly()

        post = await Wi036Post.create(title="p", user_id=user.id)
        post.title = "changed"
        await post.save()

        await user.refresh()
        assert user.updated_at is not None
        # The save() above should have bumped the parent off the year-2000 sentinel.
        assert user.updated_at.year > 2000
