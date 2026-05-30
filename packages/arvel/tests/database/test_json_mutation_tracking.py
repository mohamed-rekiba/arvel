"""In-place JSON dict mutation marks the column dirty and persists on save().

SQLAlchemy won't notice ``model.meta["k"] = v`` without a mutable type. The
``json()`` / ``jsonb()`` column helpers wrap the value so in-place dict edits
are tracked, matching the intuition that editing a JSON field then saving works.
"""

from __future__ import annotations

from typing import Any

from arvel.database import Model
from arvel.database.columns import json
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class JmtDoc(Model):
    __tablename__ = "jmt_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80))
    meta: Mapped[Any] = json(default=dict)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_in_place_dict_mutation_marks_dirty(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    doc = await JmtDoc.create(title="t", meta={"views": 0})

    doc.meta["views"] = 5

    assert doc.is_dirty("meta") is True


async def test_in_place_dict_mutation_persists(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    doc = await JmtDoc.create(title="t", meta={"views": 0})

    doc.meta["views"] = 42
    await doc.save()
    # Reload from the DB; if the in-place edit wasn't tracked, save() flushed
    # nothing and this comes back as 0.
    await session.refresh(doc, ["meta"])

    assert doc.meta["views"] == 42


async def test_in_place_list_mutation_persists(engine: AsyncEngine, session: AsyncSession) -> None:
    """A list-rooted JSON column tracks .append() in place."""
    await _setup(engine)
    doc = await JmtDoc.create(title="list", meta=["a"])

    doc.meta.append("b")
    await doc.save()
    await session.refresh(doc, ["meta"])

    assert doc.meta == ["a", "b"]
