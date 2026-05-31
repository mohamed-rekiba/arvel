"""Additional Model + SoftDeletes coverage — restore, force_delete, refresh, fresh."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, SoftDeletes, Timestamps, id_, string
from sqlalchemy.ext.asyncio import AsyncSession


class Doc(Model, Timestamps, SoftDeletes):
    __tablename__ = "docs_m"
    id: int = id_()
    title: str = string(120)


class HardOnly(Model, Timestamps):
    __tablename__ = "hard_only"
    id: int = id_()
    name: str = string(80)


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


async def test_bulk_delete_soft_deletes_on_softdelete_model(
    engine: Any, session: AsyncSession
) -> None:
    await _setup(engine)
    a = await Doc.create(title="keep")
    b = await Doc.create(title="drop")
    n = await Doc.where(title="drop").delete()
    assert n == 1
    # Soft-deleted: gone from default scope, still present with_trashed.
    # Assert via SQL aggregates — bulk UPDATE doesn't refresh in-memory instances.
    assert await Doc.find(b.id) is None
    assert await Doc.only_trashed().where(title="drop").count() == 1
    assert await Doc.find(a.id) is not None


async def test_bulk_force_delete_hard_removes_softdelete_model(
    engine: Any, session: AsyncSession
) -> None:
    await _setup(engine)
    await Doc.create(title="gone")
    n = await Doc.where(title="gone").force_delete()
    assert n == 1
    assert await Doc.with_trashed().where(title="gone").first() is None


async def test_bulk_delete_hard_when_no_softdeletes(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    await HardOnly.create(name="bulk")
    n = await HardOnly.where(name="bulk").delete()
    assert n == 1
    assert await HardOnly.where(name="bulk").count() == 0
