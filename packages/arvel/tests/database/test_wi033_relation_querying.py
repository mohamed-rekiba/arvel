"""WI-arvel-033 — Epic 007 Story 8: relation-querying completeness.

Nested where_has, or_* relation variants, constrained doesnt_have, operator+count where_has,
with_where_has, and where_belongs_to.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from arvel.database import Model
from arvel.database.query import QueryBuilder
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

_Constraint = Callable[[QueryBuilder[Any]], QueryBuilder[Any]]


class Wi033User(Model):
    __tablename__ = "wi033_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    posts: Mapped[list[Wi033Post]] = relationship(
        "Wi033Post", back_populates="author", init=False, default_factory=list
    )


class Wi033Post(Model):
    __tablename__ = "wi033_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120))
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wi033_users.id"), default=None
    )
    author: Mapped[Wi033User | None] = relationship(
        "Wi033User", back_populates="posts", init=False
    )
    comments: Mapped[list[Wi033Comment]] = relationship(
        "Wi033Comment", back_populates="post", init=False, default_factory=list
    )


class Wi033Comment(Model):
    __tablename__ = "wi033_comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str] = mapped_column(String(200))
    spam: Mapped[bool] = mapped_column(default=False)
    post_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wi033_posts.id"), default=None
    )
    post: Mapped[Wi033Post | None] = relationship(
        "Wi033Post", back_populates="comments", init=False
    )


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestNestedWhereHas:
    async def test_walks_both_hops(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        u_has = await Wi033User.create(name="has")
        u_none = await Wi033User.create(name="none")
        p1 = await Wi033Post.create(title="p1", user_id=u_has.id)
        await Wi033Post.create(title="p2", user_id=u_none.id)  # post, but no comments
        await Wi033Comment.create(body="hi", post_id=p1.id)

        names = [u.name for u in await Wi033User.query().where_has("posts.comments").get()]
        assert names == ["has"]

    async def test_nested_with_leaf_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        u = await Wi033User.create(name="u")
        p = await Wi033Post.create(title="p", user_id=u.id)
        await Wi033Comment.create(body="ham", post_id=p.id, spam=False)

        match = await Wi033User.query().where_has(
            "posts.comments", lambda q: q.where(Wi033Comment.spam == False)  # noqa: E712
        ).get()
        assert [x.name for x in match] == ["u"]

        none = await Wi033User.query().where_has(
            "posts.comments", lambda q: q.where(Wi033Comment.spam == True)  # noqa: E712
        ).get()
        assert none == []


class TestOperatorCount:
    async def test_where_has_with_count(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        few = await Wi033Post.create(title="few")
        many = await Wi033Post.create(title="many")
        await Wi033Comment.create(body="a", post_id=few.id)
        for i in range(3):
            await Wi033Comment.create(body=f"m{i}", post_id=many.id)

        titles = [
            p.title for p in await Wi033Post.query().where_has("comments", None, ">=", 3).get()
        ]
        assert titles == ["many"]

    async def test_where_has_count_with_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p = await Wi033Post.create(title="p")
        await Wi033Comment.create(body="ham1", post_id=p.id, spam=False)
        await Wi033Comment.create(body="ham2", post_id=p.id, spam=False)
        await Wi033Comment.create(body="spam", post_id=p.id, spam=True)

        # 2 non-spam comments → matches >= 2, not >= 3.
        c: _Constraint = lambda q: q.where(Wi033Comment.spam == False)  # noqa: E712, E731
        matched = await Wi033Post.query().where_has("comments", c, ">=", 2).get()
        assert [x.title for x in matched] == ["p"]
        assert await Wi033Post.query().where_has("comments", c, ">=", 3).get() == []


class TestOrVariants:
    async def test_or_where_has(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        commented = await Wi033Post.create(title="commented")
        await Wi033Post.create(title="special")
        await Wi033Post.create(title="ignored")
        await Wi033Comment.create(body="x", post_id=commented.id)

        rows = await (
            Wi033Post.query()
            .where(Wi033Post.title == "special")
            .or_where_has("comments")
            .get()
        )
        assert {p.title for p in rows} == {"commented", "special"}

    async def test_or_doesnt_have(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        await Wi033Post.create(title="empty")
        full = await Wi033Post.create(title="full")
        await Wi033Comment.create(body="x", post_id=full.id)

        rows = await (
            Wi033Post.query()
            .where(Wi033Post.title == "nonexistent")
            .or_doesnt_have("comments")
            .get()
        )
        assert {p.title for p in rows} == {"empty"}

    async def test_or_where_relation(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p1 = await Wi033Post.create(title="p1")
        p2 = await Wi033Post.create(title="p2")
        await Wi033Comment.create(body="keeper", post_id=p1.id)
        await Wi033Comment.create(body="other", post_id=p2.id)

        rows = await (
            Wi033Post.query()
            .where(Wi033Post.title == "nope")
            .or_where_relation("comments", "body", "keeper")
            .get()
        )
        assert {p.title for p in rows} == {"p1"}


class TestDoesntHaveConstraint:
    async def test_doesnt_have_with_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        # Post whose only comment is spam → "doesn't have a non-spam comment".
        spam_only = await Wi033Post.create(title="spam_only")
        ham = await Wi033Post.create(title="ham")
        await Wi033Comment.create(body="s", post_id=spam_only.id, spam=True)
        await Wi033Comment.create(body="h", post_id=ham.id, spam=False)

        rows = await Wi033Post.query().doesnt_have(
            "comments", lambda q: q.where(Wi033Comment.spam == False)  # noqa: E712
        ).get()
        assert {p.title for p in rows} == {"spam_only"}


class TestWithWhereHas:
    async def test_filters_and_eager_loads_with_same_constraint(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        p = await Wi033Post.create(title="p")
        empty = await Wi033Post.create(title="empty")
        await Wi033Comment.create(body="keep", post_id=p.id, spam=False)
        await Wi033Comment.create(body="drop", post_id=p.id, spam=True)
        await Wi033Comment.create(body="spam", post_id=empty.id, spam=True)

        session.expire_all()
        rows = await Wi033Post.query().with_where_has(
            "comments", lambda q: q.where(Wi033Comment.spam == False)  # noqa: E712
        ).get()
        assert [p.title for p in rows] == ["p"]
        # Eager-loaded collection is filtered by the same constraint.
        assert [c.body for c in rows[0].comments] == ["keep"]


class TestWhereBelongsTo:
    async def test_filters_by_parent_fk(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        author = await Wi033User.create(name="author")
        other = await Wi033User.create(name="other")
        await Wi033Post.create(title="mine", user_id=author.id)
        await Wi033Post.create(title="theirs", user_id=other.id)

        rows = await Wi033Post.query().where_belongs_to(author).get()
        assert [p.title for p in rows] == ["mine"]

    async def test_explicit_relation_name(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        author = await Wi033User.create(name="a")
        await Wi033Post.create(title="t", user_id=author.id)
        rows = await Wi033Post.query().where_belongs_to(author, "author").get()
        assert [p.title for p in rows] == ["t"]
