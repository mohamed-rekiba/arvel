"""Eloquent-parity (backlog 006, S4): cast-aware dirty tracking.

is_dirty/get_dirty compare cast values, not raw storage, so "1" vs 1, decimal
strings, and re-serialized JSON don't read as dirty. get_original returns the
cast value; get_raw_original returns the pre-cast committed value.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, ClassVar

from arvel.database import CastsAttributes, Model, decimal, id_, integer, string
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class AsJson(CastsAttributes):
    def get(self, model: Any, key: str, value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    def set(self, model: Any, key: str, value: Any) -> Any:
        return value if isinstance(value, str) else json.dumps(value)


class Toggle(Model):
    __tablename__ = "dirty_toggles"
    __casts__: ClassVar[dict[str, Any]] = {
        "active": "boolean",
        "amount": "decimal:2",
        "meta": AsJson,
    }
    id: int = id_()
    active: Any = integer(default=0)
    amount: Any = decimal(10, 2, default=Decimal(0))
    meta: Any = string(500, default="{}")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_boolean_over_int_not_dirty_when_semantically_equal(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="1.00", meta={"a": 1})
    reloaded = await Toggle.query().where(Toggle.id == t.id).first()
    assert reloaded is not None
    # committed raw is 1 (int); assigning the bool back must not read as dirty.
    reloaded.active = True
    assert reloaded.is_dirty("active") is False
    reloaded.active = "1"
    assert reloaded.is_dirty("active") is False


async def test_boolean_actually_changed_is_dirty(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="1.00", meta={"a": 1})
    t.active = False
    assert t.is_dirty("active") is True
    assert t.get_dirty()["active"] is False


async def test_decimal_string_not_dirty(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="10.50", meta={"a": 1})
    reloaded = await Toggle.query().where(Toggle.id == t.id).first()
    assert reloaded is not None
    reloaded.amount = "10.5"  # same value, different string
    assert reloaded.is_dirty("amount") is False


async def test_reserialized_json_not_dirty(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="1.00", meta={"a": 1, "b": 2})
    reloaded = await Toggle.query().where(Toggle.id == t.id).first()
    assert reloaded is not None
    # Different key order serializes to a different string but the same dict.
    reloaded.meta = {"b": 2, "a": 1}
    assert reloaded.is_dirty("meta") is False
    reloaded.meta = {"a": 99}
    assert reloaded.is_dirty("meta") is True


async def test_get_raw_original_returns_precast_value(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="1.00", meta={"a": 1})
    reloaded = await Toggle.query().where(Toggle.id == t.id).first()
    assert reloaded is not None
    reloaded.active = False
    assert reloaded.get_raw_original("active") == 1  # stored int, pre-cast


async def test_get_original_returns_cast_value(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="1.00", meta={"a": 1})
    reloaded = await Toggle.query().where(Toggle.id == t.id).first()
    assert reloaded is not None
    reloaded.active = False
    assert reloaded.get_original("active") is True  # cast value, not raw 1
    assert reloaded.get_original("meta") == {"a": 1}


async def test_original_is_equivalent_direct(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    t = await Toggle.create(active=True, amount="1.00", meta={"a": 1})
    reloaded = await Toggle.query().where(Toggle.id == t.id).first()
    assert reloaded is not None
    reloaded.active = "1"
    assert reloaded.original_is_equivalent("active") is True
    reloaded.active = False
    assert reloaded.original_is_equivalent("active") is False
