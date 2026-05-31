"""WI-arvel-022 — Epic 006 Story 10: soft-delete upsert + bulk restore.

Covers ``restore_or_create`` / ``create_or_restore``, bulk ``QueryBuilder.restore()``,
the instance ``trashed()`` helper, and ``force_destroy(ids)``.
"""

from __future__ import annotations

from arvel.database import Model
from arvel.database.model import SoftDeletes
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Wi022Account(Model, SoftDeletes):
    __tablename__ = "wi022_accounts"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    email: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(120), default="")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestTrashedHelper:
    async def test_trashed_reflects_deleted_at(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        acct = await Wi022Account.create(email="a@x.io", name="A")
        assert acct.trashed() is False
        await acct.delete()
        assert acct.trashed() is True


class TestRestoreOrCreate:
    async def test_restores_trashed_instead_of_duplicating(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        acct = await Wi022Account.create(email="dup@x.io", name="orig")
        await acct.delete()

        restored = await Wi022Account.restore_or_create({"email": "dup@x.io"}, {"name": "new"})
        assert restored.id == acct.id
        assert restored.trashed() is False
        # Only one row total (no duplicate created).
        assert len(await Wi022Account.with_trashed().get()) == 1

    async def test_returns_existing_live_row(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        acct = await Wi022Account.create(email="live@x.io", name="L")
        same = await Wi022Account.restore_or_create({"email": "live@x.io"})
        assert same.id == acct.id

    async def test_creates_when_missing(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        made = await Wi022Account.restore_or_create({"email": "new@x.io"}, {"name": "N"})
        assert made.id is not None
        assert made.name == "N"

    async def test_create_or_restore_alias(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        acct = await Wi022Account.create(email="alias@x.io", name="A")
        await acct.delete()
        restored = await Wi022Account.create_or_restore({"email": "alias@x.io"})
        assert restored.id == acct.id
        assert restored.trashed() is False


class TestBulkRestore:
    async def test_only_trashed_restore_clears_all(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi022Account.create(email="a@x.io", name="a")
        b = await Wi022Account.create(email="b@x.io", name="b")
        await a.delete()
        await b.delete()

        count = await Wi022Account.only_trashed().restore()
        assert count == 2
        # All rows visible again under the default scope.
        assert len(await Wi022Account.all()) == 2


class TestForceDestroy:
    async def test_force_destroy_removes_including_trashed(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi022Account.create(email="a@x.io", name="a")
        b = await Wi022Account.create(email="b@x.io", name="b")
        await a.delete()  # trashed

        removed = await Wi022Account.force_destroy([a.id, b.id])
        assert removed == 2
        assert len(await Wi022Account.with_trashed().get()) == 0

    async def test_force_destroy_varargs(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Wi022Account.create(email="a@x.io", name="a")
        removed = await Wi022Account.force_destroy(a.id)
        assert removed == 1
