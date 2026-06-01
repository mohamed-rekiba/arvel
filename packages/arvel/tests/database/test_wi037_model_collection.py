"""Eloquent-style ModelCollection.

all/get return a ModelCollection with batch load, model_keys, PK-aware
find/contains/only/except_/diff/intersect, to_query, fresh, make_hidden/make_visible."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, ModelCollection, foreign_id, id_, relationship, string
from arvel.database.exceptions import UnknownRelationError
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Wi037User(Model):
    __tablename__ = "wi037_users"
    id: int = id_()
    name: str = string(80, default="")
    secret: str = string(80, default="")
    posts: list[Wi037Post] = relationship(
        "Wi037Post", back_populates="author", init=False, default_factory=list
    )


class Wi037Post(Model):
    __tablename__ = "wi037_posts"
    id: int = id_()
    title: str = string(120, default="")
    user_id: int | None = foreign_id("wi037_users.id", nullable=True)
    author: Wi037User | None = relationship("Wi037User", back_populates="posts", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class _SelectCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _conn: Connection, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1


class TestType:
    async def test_all_returns_model_collection(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await Wi037User.create(name="a")
        assert isinstance(await Wi037User.query().get(), ModelCollection)
        assert isinstance(await Wi037User.all(), ModelCollection)


class TestModelKeys:
    async def test_model_keys_and_find_and_contains(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi037User.create(name="a")
        b = await Wi037User.create(name="b")
        users = await Wi037User.query().order_by("id").get()

        assert users.model_keys() == [a.id, b.id]
        assert users.find(b.id) is not None
        assert users.find(b.id).name == "b"
        assert users.find(999) is None
        assert users.contains(a.id) is True
        assert users.contains(999) is False

        def is_b(user: Wi037User) -> bool:
            return user.name == "b"

        assert users.contains(is_b) is True


class TestSetOps:
    async def test_only_except_diff_intersect(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi037User.create(name="a")
        b = await Wi037User.create(name="b")
        c = await Wi037User.create(name="c")
        users = await Wi037User.query().order_by("id").get()

        assert users.only(a.id, c.id).model_keys() == [a.id, c.id]
        assert users.except_(b.id).model_keys() == [a.id, c.id]

        subset = await Wi037User.query().where(Wi037User.__table__.c.id == b.id).get()
        assert users.diff(subset).model_keys() == [a.id, c.id]
        assert users.intersect(subset).model_keys() == [b.id]


class TestLoad:
    async def test_load_batches_relation(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        u1 = await Wi037User.create(name="u1")
        u2 = await Wi037User.create(name="u2")
        await Wi037Post.create(title="p1", user_id=u1.id)
        await Wi037Post.create(title="p2", user_id=u2.id)
        session.expire_all()

        users = await Wi037User.query().order_by("id").get()

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            await users.load("posts")
            # parent re-select + one selectin batch for all members' posts (not N+1)
            assert counter.count == 2
            before = counter.count
            _ = [p.title for p in users[0].posts]
            assert counter.count == before  # served from cache
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)

        assert users[0].posts[0].title == "p1"
        assert users[1].posts[0].title == "p2"

    async def test_load_unknown_relation_raises(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await Wi037User.create(name="a")
        users = await Wi037User.get()
        with pytest.raises(UnknownRelationError):
            await users.load("not_a_relation")


class TestLoadMissing:
    async def test_load_missing_skips_already_loaded(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        u1 = await Wi037User.create(name="u1")
        await Wi037Post.create(title="p1", user_id=u1.id)
        session.expire_all()

        users = await Wi037User.query().with_("posts").get()

        counter = _SelectCounter()
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            await users.load_missing("posts")
            assert counter.count == 0  # already eager-loaded, nothing to do
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)

    async def test_load_missing_loads_when_absent(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        u1 = await Wi037User.create(name="u1")
        await Wi037Post.create(title="p1", user_id=u1.id)
        session.expire_all()

        users = await Wi037User.get()
        await users.load_missing("posts")
        assert users[0].posts[0].title == "p1"


class TestToQueryAndFresh:
    async def test_to_query_scopes_to_keys(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi037User.create(name="a")
        await Wi037User.create(name="b")
        only_a = await Wi037User.query().where(Wi037User.__table__.c.id == a.id).get()

        count = await only_a.to_query().count()
        assert count == 1

    async def test_to_query_on_empty_raises(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        empty: ModelCollection[Wi037User] = ModelCollection()
        with pytest.raises(ValueError, match="empty collection"):
            empty.to_query()

    async def test_fresh_reloads_and_preserves_order(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi037User.create(name="a")
        b = await Wi037User.create(name="b")
        users = await Wi037User.query().order_by("id").get()

        await Wi037User.query().where(Wi037User.__table__.c.id == a.id).update({"name": "renamed"})

        fresh = await users.fresh()
        assert fresh.model_keys() == [a.id, b.id]
        assert fresh.find(a.id).name == "renamed"


class TestVisibility:
    async def test_make_hidden_and_visible(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await Wi037User.create(name="a", secret="x")
        users = await Wi037User.get()

        users.make_hidden("secret")
        assert "secret" not in users[0].to_dict()

        users.make_visible("secret")
        assert "secret" in users[0].to_dict()
