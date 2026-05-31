"""WI-arvel-021 — Epic 006 Story 12: timestamp controls.

Covers ``__timestamps__`` opt-out, custom ``CREATED_AT`` / ``UPDATED_AT`` columns,
``touch`` / ``touch_quietly``, and the ``without_timestamps`` context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from arvel.database import Model, Observer
from arvel.database.columns import datetime as ts_column
from arvel.database.events import clear_observers
from arvel.database.model import Timestamps
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Wi021Stamped(Model, Timestamps):
    __tablename__ = "wi021_stamped"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), default="")


class Wi021NoStamps(Model):
    __tablename__ = "wi021_no_stamps"
    __timestamps__ = False
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    created_at: Mapped[datetime | None] = ts_column(nullable=True, init=False, default=None)
    updated_at: Mapped[datetime | None] = ts_column(nullable=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), default="")


class Wi021Custom(Model):
    __tablename__ = "wi021_custom"
    CREATED_AT: ClassVar[str] = "inserted_at"
    UPDATED_AT: ClassVar[str] = "changed_at"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    inserted_at: Mapped[datetime | None] = ts_column(nullable=True, init=False, default=None)
    changed_at: Mapped[datetime | None] = ts_column(nullable=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), default="")


class Wi021Nullable(Model):
    """Nullable timestamp columns so ``without_timestamps`` can leave them empty."""

    __tablename__ = "wi021_nullable"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    created_at: Mapped[datetime | None] = ts_column(nullable=True, init=False, default=None)
    updated_at: Mapped[datetime | None] = ts_column(nullable=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), default="")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestTimestampToggle:
    async def test_default_fills_both_on_insert(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        row = await Wi021Stamped.create(title="a")
        assert row.created_at is not None
        assert row.updated_at is not None

    async def test_updated_at_bumps_on_save(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        row = await Wi021Stamped.create(title="a")
        first = row.updated_at
        object.__setattr__(row, "updated_at", datetime(2000, 1, 1, tzinfo=UTC))
        row.title = "b"
        await row.save()
        assert row.updated_at != datetime(2000, 1, 1, tzinfo=UTC)
        assert row.updated_at >= first

    async def test_timestamps_false_skips_fill(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        row = await Wi021NoStamps.create(title="a")
        assert row.created_at is None
        assert row.updated_at is None


class TestCustomColumns:
    async def test_custom_columns_filled(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        row = await Wi021Custom.create(title="a")
        assert row.inserted_at is not None
        assert row.changed_at is not None


class TestTouch:
    async def test_touch_bumps_updated_at(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        row = await Wi021Stamped.create(title="a")
        object.__setattr__(row, "updated_at", datetime(2000, 1, 1, tzinfo=UTC))
        await row.touch()
        assert row.updated_at.year != 2000

    async def test_touch_named_attribute(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        row = await Wi021Custom.create(title="a")
        await row.touch("inserted_at")
        # The named column and the auto-bumped UPDATED_AT both advance.
        assert row.inserted_at is not None
        assert row.changed_at is not None

    async def test_touch_quietly_skips_events(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        clear_observers(Wi021Stamped)
        fired: list[str] = []

        class _Spy(Observer["Wi021Stamped"]):
            def updated(self, instance: Wi021Stamped) -> None:
                fired.append(instance.title)

        Wi021Stamped.observe(_Spy())
        row = await Wi021Stamped.create(title="a")
        await row.touch_quietly()
        assert fired == []
        clear_observers(Wi021Stamped)


class TestWithoutTimestamps:
    async def test_block_skips_timestamp_fill(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        async with Wi021Nullable.without_timestamps():
            row = await Wi021Nullable.create(title="a")
        assert row.created_at is None
        assert row.updated_at is None

    async def test_restores_after_block(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        async with Wi021Nullable.without_timestamps():
            await Wi021Nullable.create(title="quiet")
        row = await Wi021Nullable.create(title="loud")
        assert row.created_at is not None
