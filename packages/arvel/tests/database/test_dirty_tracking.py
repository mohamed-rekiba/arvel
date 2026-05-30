"""Eloquent-style dirty tracking and $appends on the model.

is_dirty / get_dirty / get_original / was_changed / get_changes mirror Laravel's
attribute change tracking. __appends__ adds @accessor values to to_dict() output.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.database import Model, Timestamps, accessor
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Widget(Model, Timestamps):
    __tablename__ = "dirty_widgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    price: Mapped[int] = mapped_column(Integer, default=0)

    __appends__: ClassVar[list[str] | None] = ["label"]

    @accessor
    def label(self) -> str:
        return f"{self.name} (${self.price})"


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestDirtyTracking:
    async def test_fresh_instance_after_save_is_clean(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        assert w.is_clean()
        assert w.is_dirty() is False
        assert w.get_dirty() == {}

    async def test_mutating_attribute_marks_dirty(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        w.price = 25
        assert w.is_dirty() is True
        assert w.is_dirty("price") is True
        assert w.is_dirty("name") is False
        assert w.get_dirty() == {"price": 25}

    async def test_get_original_returns_loaded_value(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        w.price = 25
        assert w.get_original("price") == 10
        assert w.get_original()["price"] == 10

    async def test_save_clears_dirty_state(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        w.price = 25
        await w.save()
        assert w.is_clean()
        assert w.get_original("price") == 25

    async def test_was_changed_reflects_last_save(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        w.price = 25
        await w.save()
        assert w.was_changed("price") is True
        assert w.was_changed("name") is False
        assert w.get_changes() == {"price": 25}

    async def test_sync_original_resets_baseline(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        w.price = 99
        w.sync_original()
        assert w.is_clean()
        assert w.get_original("price") == 99


class TestAppends:
    async def test_appends_accessor_in_to_dict(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        data = w.to_dict()
        assert data["label"] == "gizmo ($10)"
        assert data["name"] == "gizmo"

    async def test_appended_attribute_respects_hidden(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        w = await Widget.create(name="gizmo", price=10)
        w.make_hidden("label")
        assert "label" not in w.to_dict()
