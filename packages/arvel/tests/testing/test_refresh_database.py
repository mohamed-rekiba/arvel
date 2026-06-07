"""Smoke tests for the RefreshDatabase mixin."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, id_, string
from arvel.database.session import get_optional_session
from arvel.testing.refresh_database import RefreshDatabase


class _Widget(Model):
    __tablename__ = "refresh_db_widgets"
    id: int = id_()
    name: str = string(255)


class _StubContainer:
    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def make(self, _type: object) -> Any:
        return self._engine


class _StubApp:
    def __init__(self, engine: Any) -> None:
        self.container = _StubContainer(engine)


class _Case(RefreshDatabase):
    """Minimal harness — no ArvelTestCase, just the mixin."""

    def __init__(self, engine: Any) -> None:
        self.app = _StubApp(engine)


@pytest.mark.asyncio
async def test_refresh_database_binds_active_session(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_Widget.metadata.create_all)

    case = _Case(engine)
    await case._refresh_database_setup()  # pyright: ignore[reportPrivateUsage]
    try:
        active = get_optional_session()
        assert active is not None
        await _Widget(name="alpha").save()
        # Active session sees what it just wrote.
        rows = await _Widget.all()
        assert [w.name for w in rows] == ["alpha"]
    finally:
        await case._refresh_database_teardown()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_refresh_database_rolls_back_on_teardown(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_Widget.metadata.create_all)

    case = _Case(engine)
    await case._refresh_database_setup()  # pyright: ignore[reportPrivateUsage]
    await _Widget(name="ghost").save()
    await case._refresh_database_teardown()  # pyright: ignore[reportPrivateUsage]

    # After teardown, the row is gone — open a fresh connection and look.
    from sqlalchemy import select

    async with engine.connect() as conn:
        result = await conn.execute(select(_Widget.__table__))
        rows = result.fetchall()
    assert rows == []


@pytest.mark.asyncio
async def test_refresh_database_is_noop_without_engine() -> None:
    class _NoEngineApp:
        container = None

    class _NoEngineCase(RefreshDatabase):
        def __init__(self) -> None:
            self.app = _NoEngineApp()

    case = _NoEngineCase()
    # Should not raise.
    await case._refresh_database_setup()  # pyright: ignore[reportPrivateUsage]
    await case._refresh_database_teardown()  # pyright: ignore[reportPrivateUsage]
