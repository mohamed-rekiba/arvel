"""Tests for Story 2: Fluent Query Builder + Epic 13c Story 9: Safety.

Covers: FR-044 through FR-049, NFR-019, NFR-021.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast

import pytest

from .conftest import Post, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TestQueryBuilderBasic:
    """FR-044: Query builder produces parameterized SQL and returns typed instances."""

    async def test_query_first_returns_instance(self, db_session: AsyncSession) -> None:
        db_session.add(User(name="Alice", email="alice@qb.com"))
        await db_session.flush()

        result = (
            await User.query(db_session)
            .where(User.email == "alice@qb.com")
            .order_by(User.id)
            .first()
        )
        assert result is not None
        assert isinstance(result, User)
        assert result.name == "Alice"

    async def test_query_first_returns_none_when_no_match(self, db_session: AsyncSession) -> None:
        result = (
            await User.query(db_session)
            .where(User.email == "nonexistent@qb.com")
            .order_by(User.id)
            .first()
        )
        assert result is None

    async def test_query_all_returns_list(self, db_session: AsyncSession) -> None:
        db_session.add_all(
            [
                User(name="A", email="a@qb.com"),
                User(name="B", email="b@qb.com"),
            ]
        )
        await db_session.flush()

        results = await User.query(db_session).all()
        assert isinstance(results, list)
        assert len(results) >= 2
        assert all(isinstance(u, User) for u in results)


class TestQueryBuilderWhereChaining:
    """FR-045: Multiple .where() calls are AND-ed."""

    async def test_chained_where_ands_conditions(self, db_session: AsyncSession) -> None:
        db_session.add_all(
            [
                User(name="Young Active", email="ya@qb.com", age=20, active=True),
                User(name="Young Inactive", email="yi@qb.com", age=20, active=False),
                User(name="Old Active", email="oa@qb.com", age=50, active=True),
            ]
        )
        await db_session.flush()

        results = (
            await User.query(db_session)
            .where(User.age == 20)
            .where(User.active == True)  # noqa: E712
            .all()
        )
        assert len(results) == 1
        assert results[0].name == "Young Active"


class TestQueryBuilderOrderBy:
    """FR-046: .order_by() sorts results."""

    async def test_order_by_ascending(self, db_session: AsyncSession) -> None:
        db_session.add_all(
            [
                User(name="Charlie", email="c@ob.com"),
                User(name="Alice", email="a@ob.com"),
                User(name="Bob", email="b@ob.com"),
            ]
        )
        await db_session.flush()

        results = await User.query(db_session).order_by(User.name).all()
        names = [u.name for u in results]
        assert names == sorted(names)

    async def test_order_by_descending(self, db_session: AsyncSession) -> None:
        db_session.add_all(
            [
                User(name="Charlie", email="c@obd.com"),
                User(name="Alice", email="a@obd.com"),
            ]
        )
        await db_session.flush()

        results = await User.query(db_session).order_by(User.name.desc()).all()
        names = [u.name for u in results]
        assert names == sorted(names, reverse=True)


class TestQueryBuilderPagination:
    """FR-047: .limit() and .offset() paginate results."""

    async def test_limit(self, db_session: AsyncSession) -> None:
        for i in range(5):
            db_session.add(User(name=f"User{i}", email=f"u{i}@lim.com"))
        await db_session.flush()

        results = await User.query(db_session).limit(3).all()
        assert len(results) == 3

    async def test_offset(self, db_session: AsyncSession) -> None:
        for i in range(5):
            db_session.add(User(name=f"User{i}", email=f"u{i}@off.com"))
        await db_session.flush()

        all_results = await User.query(db_session).order_by(User.id).all()
        offset_results = await User.query(db_session).order_by(User.id).offset(2).all()
        assert offset_results[0].id == all_results[2].id

    async def test_limit_and_offset(self, db_session: AsyncSession) -> None:
        for i in range(10):
            db_session.add(User(name=f"User{i}", email=f"u{i}@lo.com"))
        await db_session.flush()

        results = await User.query(db_session).order_by(User.id).limit(3).offset(5).all()
        assert len(results) == 3


class TestQueryBuilderEagerLoading:
    """FR-048: .with_() eager-loads relationships."""

    async def test_eager_load_posts(self, db_session: AsyncSession) -> None:
        user = User(name="Author", email="author@eager.com")
        db_session.add(user)
        await db_session.flush()

        for i in range(3):
            db_session.add(Post(title=f"Post {i}", user_id=user.id))
        await db_session.flush()

        result = (
            await User.query(db_session)
            .where(User.email == "author@eager.com")
            .with_("posts")
            .order_by(User.id)
            .first()
        )
        assert result is not None
        assert len(result.posts) == 3

    async def test_eager_load_author_on_post(self, db_session: AsyncSession) -> None:
        user = User(name="Writer", email="writer@eager.com")
        db_session.add(user)
        await db_session.flush()

        post = Post(title="My Post", user_id=user.id)
        db_session.add(post)
        await db_session.flush()

        result = (
            await Post.query(db_session)
            .where(Post.title == "My Post")
            .with_("author")
            .order_by(Post.id)
            .first()
        )
        assert result is not None
        assert result.author.name == "Writer"


class TestQueryBuilderCount:
    """Query builder supports .count() for aggregate queries."""

    async def test_count_returns_integer(self, db_session: AsyncSession) -> None:
        db_session.add_all(
            [
                User(name="A", email="a@cnt.com"),
                User(name="B", email="b@cnt.com"),
            ]
        )
        await db_session.flush()

        count = await User.query(db_session).count()
        assert isinstance(count, int)
        assert count >= 2

    async def test_count_with_filter(self, db_session: AsyncSession) -> None:
        db_session.add_all(
            [
                User(name="Active", email="active@cnt.com", active=True),
                User(name="Inactive", email="inactive@cnt.com", active=False),
            ]
        )
        await db_session.flush()

        count = await User.query(db_session).where(User.active == True).count()  # noqa: E712
        assert count >= 1


class TestQueryBuilderParameterized:
    """NFR-021: All queries use parameterized statements."""

    async def test_where_uses_bound_params(self, db_session: AsyncSession) -> None:
        qb = User.query(db_session).where(User.email == "test@param.com")
        stmt = qb.build_statement()
        compiled = stmt.compile()
        assert "test@param.com" not in str(compiled)
        assert len(compiled.params) > 0


class TestQueryBuilderSafety:
    """Epic 13c Story 9: Query builder safety hardening."""

    async def test_first_without_order_by_warns(self, db_session: AsyncSession) -> None:
        """first() without order_by() emits a warning about non-deterministic results."""
        db_session.add(User(name="Warn", email="warn@safety.com"))
        await db_session.flush()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await User.query(db_session).where(User.email == "warn@safety.com").first()
            assert len(w) == 1
            assert "non-deterministic" in str(w[0].message)
            assert "order_by()" in str(w[0].message)

    async def test_first_with_order_by_no_warning(self, db_session: AsyncSession) -> None:
        """first() with order_by() doesn't warn."""
        db_session.add(User(name="NoWarn", email="nowarn@safety.com"))
        await db_session.flush()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await User.query(db_session).order_by(User.id).first()
            order_warnings = [x for x in w if "non-deterministic" in str(x.message)]
            assert len(order_warnings) == 0

    async def test_with_invalid_relationship_raises(self, db_session: AsyncSession) -> None:
        """with_() raises ValueError for invalid relationship name."""
        with pytest.raises(ValueError, match="has no attribute"):
            User.query(db_session).with_("nonexistent")

    async def test_has_invalid_relationship_raises(self, db_session: AsyncSession) -> None:
        """has() raises ValueError for invalid relationship name."""
        with pytest.raises(ValueError, match="has no relationship"):
            User.query(db_session).has("nonexistent")

    async def test_has_invalid_operator_raises(self, db_session: AsyncSession) -> None:
        """has() raises ValueError for invalid comparison operator."""
        with pytest.raises(ValueError, match="Unsupported comparison operator"):
            User.query(db_session).has("posts", cast("Any", "LIKE"), 1)

    async def test_chained_where_ands(self, db_session: AsyncSession) -> None:
        """Multiple where() calls are AND-ed (idempotent chaining)."""
        db_session.add(User(name="ChainA", email="chaina@safety.com", age=25, active=True))
        db_session.add(User(name="ChainB", email="chainb@safety.com", age=25, active=False))
        await db_session.flush()

        results = (
            await User.query(db_session)
            .where(User.age == 25)
            .where(User.active == True)  # noqa: E712
            .where(User.email == "chaina@safety.com")
            .all()
        )
        assert len(results) == 1
        assert results[0].name == "ChainA"

    def test_to_sql_raises_without_debug_mode(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """to_sql() raises RuntimeError when ARVEL_DEBUG is not true."""
        monkeypatch.delenv("ARVEL_DEBUG", raising=False)
        qb = User.query(db_session).where(User.name == "test")
        with pytest.raises(RuntimeError, match="ARVEL_DEBUG"):
            qb.to_sql()

    def test_to_sql_returns_sql_in_debug_mode(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """to_sql() returns SQL string when ARVEL_DEBUG=true."""
        monkeypatch.setenv("ARVEL_DEBUG", "true")
        qb = User.query(db_session).where(User.name == "test")
        sql = qb.to_sql()
        assert isinstance(sql, str)
        assert "users" in sql.lower()
        assert "SELECT" in sql.upper() or "select" in sql.lower()
