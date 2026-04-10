"""Tests for query scopes — local, parameterized, and global."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest
from sqlalchemy import String, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.collection import ArvelCollection
from arvel.data.model import ArvelModel
from arvel.data.scopes import GlobalScope, scope

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# ──── Models with scopes ────


class ActiveScope(GlobalScope):
    """Global scope that filters to active records only."""

    def apply(self, query):
        return query.where(ScopedUser.is_active.is_(True))


class ScopedUser(ArvelModel):
    __tablename__ = "scoped_users"
    __global_scopes__: ClassVar[list] = [ActiveScope()]

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    role: Mapped[str] = mapped_column(String(50), default="user")

    @scope
    @staticmethod
    def admins(query):
        return query.where(ScopedUser.role == "admin")

    @scope
    @staticmethod
    def older_than(query, age: int):
        return query.where(ScopedUser.age > age)

    @scope
    @staticmethod
    def scope_named_with_prefix(query):
        """Scope with the ``scope_`` prefix — should be registered as ``named_with_prefix``."""
        return query.where(ScopedUser.name != "")


class UnscopedUser(ArvelModel):
    """Model without global scopes for comparison."""

    __tablename__ = "unscoped_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)


# ──── Fixtures ────


@pytest.fixture(scope="module", params=["asyncio"], autouse=True)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
async def scope_session() -> AsyncGenerator[AsyncSession]:
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


async def _seed_scoped_users(session: AsyncSession) -> None:
    session.add_all(
        [
            ScopedUser(name="Alice", age=30, is_active=True, role="admin"),
            ScopedUser(name="Bob", age=25, is_active=True, role="user"),
            ScopedUser(name="Charlie", age=35, is_active=False, role="admin"),
            ScopedUser(name="Diana", age=28, is_active=True, role="user"),
            ScopedUser(name="Eve", age=40, is_active=False, role="user"),
        ]
    )
    await session.flush()


# ──── Local scope tests ────


class TestLocalScopes:
    async def test_local_scope_filters_results(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).admins().all()
        assert isinstance(result, ArvelCollection)
        assert all(u.role == "admin" for u in result)

    async def test_parameterized_scope(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).older_than(30).all()
        assert all(u.age > 30 for u in result)

    async def test_chained_scopes(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).admins().older_than(25).all()
        assert all(u.role == "admin" and u.age > 25 for u in result)

    async def test_scope_prefix_stripped(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).named_with_prefix().all()
        assert isinstance(result, ArvelCollection)

    async def test_unknown_scope_raises_attribute_error(self, scope_session: AsyncSession) -> None:
        with pytest.raises(AttributeError, match="no attribute"):
            ScopedUser.query(scope_session).nonexistent_scope()


# ──── Global scope tests ────


class TestGlobalScopes:
    async def test_global_scope_applied_automatically(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).all()
        assert all(u.is_active for u in result)
        assert len(result) == 3  # Only active users

    async def test_without_global_scope_includes_all(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).without_global_scope("ActiveScope").all()
        assert len(result) == 5

    async def test_without_global_scopes_removes_all(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        result = await ScopedUser.query(scope_session).without_global_scopes().all()
        assert len(result) == 5

    async def test_global_scope_with_count(self, scope_session: AsyncSession) -> None:
        await _seed_scoped_users(scope_session)
        count = await ScopedUser.query(scope_session).count()
        assert count == 3

    async def test_model_without_global_scopes_returns_all(
        self, scope_session: AsyncSession
    ) -> None:
        session = scope_session
        session.add_all(
            [
                UnscopedUser(name="X", is_active=True),
                UnscopedUser(name="Y", is_active=False),
            ]
        )
        await session.flush()
        result = await UnscopedUser.query(session).all()
        assert len(result) == 2
