"""RefreshDatabase — Laravel-style test mixin for clean DB state per test.

Wrap each test in a transaction so writes never leak between tests. Works with
any SQLAlchemy-backed app that exposes an ``AsyncEngine`` via the container.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from arvel.database.session import reset_active_session, set_active_session

if TYPE_CHECKING:
    from contextvars import Token


class RefreshDatabase:
    """Mixin for tests that need a clean DB row state per test.

    Opens one connection, begins a transaction, binds an ``AsyncSession`` to
    that connection, and registers it as the active session. On teardown the
    transaction is rolled back — nothing the test wrote persists.

    Usage::

        class TestPosts(RefreshDatabase, ArvelTestCase):
            providers = (DatabaseServiceProvider, ...)

            async def test_create(self) -> None:
                await Post.create(title="Hi")
                # other tests never see this row

    Requires the app to bind an ``AsyncEngine`` in its container (the
    ``DatabaseServiceProvider`` does this). When no engine is bound, the mixin
    is a no-op so it can be applied liberally without breaking tests that
    don't need DB isolation.

    Optionally override ``seed`` to populate the DB before each test:

        async def seed(self) -> None:
            await DatabaseSeeder().run()
    """

    _refresh_connection: ClassVar[AsyncConnection | None] = None
    _refresh_session: ClassVar[AsyncSession | None] = None
    _refresh_token: ClassVar[Token[AsyncSession | None] | None] = None
    _refresh_trans: ClassVar[Any] = None

    async def seed(self) -> None:
        """Override to populate the database before each test."""

    async def _refresh_database_setup(self) -> None:
        engine = self._resolve_engine()
        if engine is None:
            return
        conn = await engine.connect()
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        token = set_active_session(session)
        cls = type(self)
        cls._refresh_connection = conn
        cls._refresh_session = session
        cls._refresh_token = token
        cls._refresh_trans = trans
        await self.seed()

    async def _refresh_database_teardown(self) -> None:
        cls = type(self)
        if cls._refresh_session is not None:
            with contextlib.suppress(SQLAlchemyError):
                await cls._refresh_session.close()
            cls._refresh_session = None
        if cls._refresh_trans is not None:
            with contextlib.suppress(SQLAlchemyError):
                await cls._refresh_trans.rollback()
            cls._refresh_trans = None
        if cls._refresh_connection is not None:
            with contextlib.suppress(SQLAlchemyError):
                await cls._refresh_connection.close()
            cls._refresh_connection = None
        if cls._refresh_token is not None:
            reset_active_session(cls._refresh_token)
            cls._refresh_token = None

    def _resolve_engine(self) -> AsyncEngine | None:
        app = getattr(self, "app", None)
        if app is None:
            return None
        container = getattr(app, "container", None) or app
        make: Callable[[type[AsyncEngine]], AsyncEngine] | None = getattr(container, "make", None)
        if make is None:
            return None
        with contextlib.suppress(Exception):
            return make(AsyncEngine)
        return None

    async def asyncSetUp(self) -> None:
        parent_setup: Callable[[], Awaitable[None]] | None = getattr(super(), "asyncSetUp", None)
        if callable(parent_setup):
            await parent_setup()
        await self._refresh_database_setup()

    async def asyncTearDown(self) -> None:
        try:
            await self._refresh_database_teardown()
        finally:
            parent_teardown: Callable[[], Awaitable[None]] | None = getattr(
                super(), "asyncTearDown", None
            )
            if callable(parent_teardown):
                await parent_teardown()


__all__ = ["RefreshDatabase"]
