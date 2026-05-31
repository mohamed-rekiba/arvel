"""Eloquent-parity (backlog 005, S10): streaming and chunking completeness.

stream() server-side cursor; descending keyset chunk/lazy variants; callback
early-termination via returning False; offset chunk auto-orders by PK.
"""

from __future__ import annotations

from arvel.database import Model, id_, string
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class StreamRow(Model):
    __tablename__ = "stream_rows"
    id: int = id_()
    name: str = string(40, default="")


async def _seed(engine: AsyncEngine, n: int = 5) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    for i in range(1, n + 1):
        await StreamRow.create(name=f"row-{i}")


async def test_stream_yields_all_rows(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    ids = [r.id async for r in StreamRow.query().order_by("id").stream(batch_size=2)]
    assert ids == [1, 2, 3, 4, 5]


async def test_lazy_by_id_descending(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    ids = [r.id async for r in StreamRow.query().lazy_by_id(2, descending=True)]
    assert ids == [5, 4, 3, 2, 1]


async def test_lazy_ascending_default(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    ids = [r.id async for r in StreamRow.query().lazy(2)]
    assert ids == [1, 2, 3, 4, 5]


async def test_chunk_by_id_descending(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    seen: list[int] = []

    async def collect(batch: list[StreamRow]) -> None:
        seen.extend(r.id for r in batch)

    await StreamRow.query().chunk_by_id(2, collect, descending=True)
    assert seen == [5, 4, 3, 2, 1]


async def test_chunk_callback_false_stops(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    batches: list[list[int]] = []

    async def collect(batch: list[StreamRow]) -> bool:
        batches.append([r.id for r in batch])
        return False  # stop after the first batch

    await StreamRow.query().order_by("id").chunk(2, collect)
    assert batches == [[1, 2]]


async def test_each_callback_false_stops(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    seen: list[int] = []

    async def visit(row: StreamRow) -> bool:
        seen.append(row.id)
        return row.id < 3  # stop once we hit id 3

    await StreamRow.query().order_by("id").each(visit)
    assert seen == [1, 2, 3]


async def test_chunk_without_order_auto_orders_by_pk(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine)
    seen: list[int] = []

    async def collect(batch: list[StreamRow]) -> None:
        seen.extend(r.id for r in batch)

    # No explicit order_by — must not raise and must walk PK order deterministically.
    await StreamRow.query().chunk(2, collect)
    assert seen == [1, 2, 3, 4, 5]
