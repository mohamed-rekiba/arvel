"""Shared fixtures for the arvel.data test suite.

Provides file-based SQLite engine, table creation, session-per-test
with rollback isolation, and transaction/observer fixtures.

Test models live in ``tests/_fixtures/models.py`` (single source of truth).
All async data tests run on asyncio only (aiosqlite is asyncio-native).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import filelock
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from arvel.data.model import ArvelModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from arvel.data.observer import ObserverRegistry
from arvel.data.repository import Repository
from arvel.data.transaction import Transaction
from tests._fixtures.models import (
    AppendedUser as AppendedUser,
)
from tests._fixtures.models import (
    CastUser as CastUser,
)
from tests._fixtures.models import (
    FillableUser as FillableUser,
)
from tests._fixtures.models import (
    GuardedUser as GuardedUser,
)
from tests._fixtures.models import (
    HiddenUser as HiddenUser,
)
from tests._fixtures.models import (
    MutatorUser as MutatorUser,
)
from tests._fixtures.models import (
    Post as Post,
)
from tests._fixtures.models import (
    User as User,
)
from tests._fixtures.models import (
    VisibleUser as VisibleUser,
)


@pytest.fixture(scope="module", params=["asyncio"], autouse=True)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    """Restrict data tests to asyncio (aiosqlite is asyncio-native)."""
    return request.param


# ──── Test Repositories ────


class UserRepository(Repository[User]):
    pass


class PostRepository(Repository[Post]):
    pass


class FillableUserRepository(Repository[FillableUser]):
    pass


class GuardedUserRepository(Repository[GuardedUser]):
    pass


# ──── Test Transaction ────


class AppTransaction(Transaction):
    users: UserRepository
    posts: PostRepository
    fillable_users: FillableUserRepository
    guarded_users: GuardedUserRepository


# ──── Fixtures ────

_TEMP_DIR = Path(__file__).resolve().parents[2] / ".tests" / "db"
_TEMP_DIR.mkdir(parents=True, exist_ok=True)
_TEST_DB_PATH = _TEMP_DIR / "test_data.db"
_TEST_DB_LOCK = _TEMP_DIR / "test_data.db.lock"


@pytest.fixture(scope="session", autouse=True)
def db_tables() -> None:
    """Create tables synchronously once before all tests.

    Uses filelock so multiple xdist workers don't race on table creation.
    ``checkfirst=True`` makes CREATE TABLE idempotent.
    """
    with filelock.FileLock(_TEST_DB_LOCK, timeout=30):
        sync_engine = create_engine(f"sqlite:///{_TEST_DB_PATH}", echo=False)

        @event.listens_for(sync_engine, "connect")
        def _enable_fk(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        ArvelModel.metadata.create_all(sync_engine, checkfirst=True)
        sync_engine.dispose()


@pytest.fixture
async def db_session(anyio_backend: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{_TEST_DB_PATH}", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
            if trans.is_active:
                await trans.rollback()

    await engine.dispose()


@pytest.fixture
def observer_registry() -> ObserverRegistry:
    return ObserverRegistry()


@pytest.fixture
def transaction(db_session: AsyncSession, observer_registry: ObserverRegistry) -> AppTransaction:
    return AppTransaction(session=db_session, observer_registry=observer_registry)
