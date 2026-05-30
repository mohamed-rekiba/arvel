"""Additional Model + SoftDeletes coverage — restore, force_delete, refresh, fresh."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, SoftDeletes, Timestamps
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Doc(Model, Timestamps, SoftDeletes):
    __tablename__ = "docs_m"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), nullable=False)


class HardOnly(Model, Timestamps):
    __tablename__ = "hard_only"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_restore_after_soft_delete(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    doc = await Doc.create(title="t")
    await doc.delete()
    assert doc.deleted_at is not None
    await doc.restore()
    assert doc.deleted_at is None


async def test_restore_without_soft_deletes_raises(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    hard = await HardOnly.create(name="x")
    with pytest.raises(AttributeError, match="SoftDeletes"):
        await hard.restore()


async def test_force_delete_hard_removes_soft_deleted_model(
    engine: Any, session: AsyncSession
) -> None:
    await _setup(engine)
    doc = await Doc.create(title="t")
    await doc.force_delete()
    fresh = await Doc.find(doc.id)
    assert fresh is None


async def test_fresh_returns_persisted_instance(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    doc = await Doc.create(title="t")
    refreshed = await doc.fresh()
    # `fresh()` returns the row from the identity map. Same identity → same row.
    assert refreshed is not None
    assert refreshed.id == doc.id


async def test_refresh_reloads_attrs_from_db(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    doc = await Doc.create(title="db value")
    # Simulate a stale in-memory copy by re-assigning.
    doc.title = "stale"
    await doc.refresh()
    assert doc.title == "db value"


async def test_delete_hard_when_no_softdeletes(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    hard = await HardOnly.create(name="x")
    await hard.delete()
    assert await HardOnly.find(hard.id) is None
