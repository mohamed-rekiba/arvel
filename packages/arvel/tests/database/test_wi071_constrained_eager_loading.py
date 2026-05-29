"""WI-arvel-071 — Epic 049 Story 3: constrained eager loading + query counts."""

from __future__ import annotations

import pytest
from arvel.database import Model
from arvel.database.exceptions import UnknownRelationError
from arvel.database.query_logging import QueryLog
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Wi071Country(Model):
    __tablename__ = "wi071_countries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    users: Mapped[list[Wi071User]] = relationship(
        "Wi071User", back_populates="country", init=False, default_factory=list
    )


class Wi071User(Model):
    __tablename__ = "wi071_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    country_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wi071_countries.id"), nullable=True, default=None
    )
    country: Mapped[Wi071Country | None] = relationship(
        "Wi071Country", back_populates="users", init=False
    )
    posts: Mapped[list[Wi071Post]] = relationship(
        "Wi071Post", back_populates="author", init=False, default_factory=list
    )


class Wi071Post(Model):
    __tablename__ = "wi071_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200))
    published: Mapped[bool] = mapped_column(default=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("wi071_users.id"), default=None)
    author: Mapped[Wi071User | None] = relationship("Wi071User", back_populates="posts", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestConstrainedWith:
    async def test_dict_callback_filters_eager_loaded_rows(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        mixed = await Wi071User.create(name="Mixed")
        published_only = await Wi071User.create(name="PublishedOnly")
        await Wi071Post.create(title="Live", published=True, user_id=mixed.id)
        await Wi071Post.create(title="Draft", published=False, user_id=mixed.id)
        await Wi071Post.create(title="Live2", published=True, user_id=published_only.id)

        session.expire_all()
        users = await Wi071User.with_(
            {"posts": lambda q: q.where(Wi071Post.published == True)}  # noqa: E712
        ).all()

        by_name = {u.name: u for u in users}
        assert len(by_name["Mixed"].posts) == 1
        assert by_name["Mixed"].posts[0].title == "Live"
        assert len(by_name["PublishedOnly"].posts) == 1

    async def test_mixed_string_and_dict_in_one_call(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        country = await Wi071Country.create(name="Arvelia")
        user = await Wi071User.create(name="Citizen", country_id=country.id)
        await Wi071Post.create(title="Live", published=True, user_id=user.id)
        await Wi071Post.create(title="Draft", published=False, user_id=user.id)

        session.expire_all()
        rows = await Wi071User.with_(
            {"posts": lambda q: q.where(Wi071Post.published == True)},  # noqa: E712
            "country",
        ).all()

        assert len(rows) == 1
        assert rows[0].country is not None
        assert rows[0].country.name == "Arvelia"
        assert len(rows[0].posts) == 1

    async def test_unknown_relation_in_dict_raises(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await Wi071User.create(name="Solo")

        with pytest.raises(UnknownRelationError):
            Wi071User.with_({"missing": lambda q: q})

    async def test_invalid_with_argument_type_raises(self) -> None:
        with pytest.raises(TypeError):
            Wi071User.with_(123)  # type: ignore[arg-type]


class TestEagerLoadQueryCounts:
    async def test_has_many_uses_two_queries(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        for i in range(3):
            user = await Wi071User.create(name=f"u{i}")
            await Wi071Post.create(title=f"p{i}a", user_id=user.id)
            await Wi071Post.create(title=f"p{i}b", user_id=user.id)

        with QueryLog.capture() as log:
            rows = await Wi071User.with_("posts").all()

        assert len(rows) == 3
        assert len(log.queries) == 2

    async def test_two_relations_use_three_queries(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        country = await Wi071Country.create(name="One")
        user = await Wi071User.create(name="Member", country_id=country.id)
        await Wi071Post.create(title="Post", user_id=user.id)

        with QueryLog.capture() as log:
            rows = await Wi071User.with_("posts", "country").all()

        assert len(rows) == 1
        assert len(log.queries) == 3

    async def test_belongs_to_uses_two_queries(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi071User.create(name="Author")
        for i in range(4):
            await Wi071Post.create(title=f"t{i}", user_id=user.id)

        with QueryLog.capture() as log:
            posts = await Wi071Post.with_("author").all()

        assert len(posts) == 4
        assert len(log.queries) == 2

    async def test_constrained_has_many_still_two_queries(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await Wi071User.create(name="Filtered")
        await Wi071Post.create(title="Live", published=True, user_id=user.id)
        await Wi071Post.create(title="Draft", published=False, user_id=user.id)

        session.expire_all()
        with QueryLog.capture() as log:
            rows = await Wi071User.with_(
                {"posts": lambda q: q.where(Wi071Post.published == True)}  # noqa: E712
            ).all()

        assert len(rows) == 1
        assert len(rows[0].posts) == 1
        assert len(log.queries) == 2
