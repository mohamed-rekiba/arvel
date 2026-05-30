"""NFR-003-003 + FR-003-010 — SQL injection resistance for kwarg-shorthand."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class SafeWidget(Model):
    __tablename__ = "safe_widgets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_kwarg_value_is_bound_not_interpolated(engine: Any, session: AsyncSession) -> None:
    """A classic-injection payload as a value must round-trip exactly."""
    await _create_tables(engine)
    payload = "alpha'; DROP TABLE safe_widgets; --"
    await SafeWidget.create(name=payload)

    row = await SafeWidget.where(name=payload).first()
    assert row is not None
    assert row.name == payload

    # Critically, the table still exists with intact data.
    count = await SafeWidget.count()
    assert count == 1


async def test_unknown_column_name_is_rejected_with_attribute_error(
    engine: Any, session: AsyncSession
) -> None:
    """Even an attacker-controlled column name can't be injected — it raises."""
    await _create_tables(engine)
    with pytest.raises(AttributeError):
        SafeWidget.where(**{"name; DROP TABLE x; --": "x"})


async def test_compiled_statement_contains_bound_param_marker(
    engine: Any, session: AsyncSession
) -> None:
    """The compiled SQL must use a parameter placeholder, not the literal value."""
    await _create_tables(engine)
    qb = SafeWidget.where(name="anything")
    compiled = qb._stmt.compile(dialect=engine.dialect)  # pyright: ignore[reportPrivateUsage]  # test compiles the private SQL stmt to assert parameter binding
    assert "anything" not in str(compiled)
