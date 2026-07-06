"""Vector-similarity builder clauses. The happy path needs the vector server extension and is
proven in the integration tier; here we pin the typed surface and the failure semantics on a
column without vector operators (the schema-less builder path — same getattr miss as the
portable JSON fallback)."""

from __future__ import annotations

from typing import cast

import pytest
import sqlalchemy as sa

from arvel.database.builder import UnsupportedDriverOperation, VectorMetric
from arvel.database.connections import ConnectionResolver


@pytest.fixture
async def db():
    resolver = ConnectionResolver({"default": {"url": "sqlite+aiosqlite://"}})
    async with resolver.engine().begin() as conn:
        await conn.execute(sa.text("CREATE TABLE docs(id INTEGER PRIMARY KEY, embedding TEXT)"))
    yield resolver
    await resolver.dispose()


async def test_where_vector_similar_without_vector_ops_raises(db: ConnectionResolver) -> None:
    with pytest.raises(UnsupportedDriverOperation, match="vector"):
        db.table("docs").where_vector_similar("embedding", [1.0, 0.0], max_distance=0.5)


async def test_order_by_similarity_without_vector_ops_raises(db: ConnectionResolver) -> None:
    with pytest.raises(UnsupportedDriverOperation, match="vector"):
        db.table("docs").order_by_similarity("embedding", [1.0, 0.0])


async def test_metric_map_is_closed(db: ConnectionResolver) -> None:
    # the metric is a Literal at type-check time; at runtime an off-map string cannot
    # silently pick an operator
    with pytest.raises(UnsupportedDriverOperation, match="metric"):
        db.table("docs").order_by_similarity("embedding", [1.0], metric=cast("VectorMetric", "dot"))
