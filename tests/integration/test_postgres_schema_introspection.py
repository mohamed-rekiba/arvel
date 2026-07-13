"""Schema introspection (``has_table``/``has_column``/``drop_if_exists``, doc D1) against real
PostgreSQL. Proves the fresh-inspector guarantee (DR-0044): a check run right after ``create()`` in
the *same* migration must see live catalog state, not a cached reflection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator

pytestmark = pytest.mark.integration


async def _inspect(db: ConnectionResolver, fn: Callable[[Any], Any]) -> Any:
    async with db.engine().connect() as conn:
        return await conn.run_sync(fn)


class IntrospectAndCleanUp(Migration):
    """Every assertion runs inside this one migration, right after ``create()`` — a stale/cached
    inspector would still answer ``False`` here; a fresh one (DR-0044) answers ``True``."""

    def up(self, schema: object) -> None:
        assert schema.has_table("intro_widgets") is False  # type: ignore[attr-defined]
        assert schema.has_column("intro_widgets", "name") is False  # type: ignore[attr-defined]

        schema.create(  # type: ignore[attr-defined]
            "intro_widgets", lambda t: [t.id(), t.string("name")]
        )

        assert schema.has_table("intro_widgets") is True  # type: ignore[attr-defined]
        assert schema.has_column("intro_widgets", "name") is True  # type: ignore[attr-defined]
        assert schema.has_column("intro_widgets", "no_such_column") is False  # type: ignore[attr-defined]
        assert schema.has_column("no_such_table", "anything") is False  # type: ignore[attr-defined]

        # drop_if_exists on a present table: drops it
        schema.drop_if_exists("intro_widgets")  # type: ignore[attr-defined]
        assert schema.has_table("intro_widgets") is False  # type: ignore[attr-defined]

        # drop_if_exists on the now-absent table: clean no-op, no error
        schema.drop_if_exists("intro_widgets")  # type: ignore[attr-defined]
        assert schema.has_table("intro_widgets") is False  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        schema.drop_if_exists("intro_widgets")  # type: ignore[attr-defined]


class DropAbsentTable(Migration):
    """Its own migration (own transaction): a plain ``drop()`` on an absent table still raises —
    behavior preserved, the contrast ``drop_if_exists`` exists for. Isolated from
    ``IntrospectAndCleanUp`` above so the expected Postgres error here doesn't abort *that*
    migration's transaction (Postgres poisons a transaction on any error until rollback)."""

    def up(self, schema: object) -> None:
        schema.drop("intro_widgets_never_existed")  # type: ignore[attr-defined]

    def down(self, schema: object) -> None:
        raise NotImplementedError  # never rolled back — up() always raises


async def test_schema_introspection_and_conditional_drop_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    migrator = Migrator(db)
    try:
        applied = await migrator.run([IntrospectAndCleanUp()])
        assert applied == 1

        # confirm from a separate connection too: the table really is gone, not just per-session
        exists = await _inspect(db, lambda conn: sa.inspect(conn).has_table("intro_widgets"))
        assert exists is False

        # contrast, in its own transaction: plain drop() on an absent table still raises
        with pytest.raises(Exception, match=r"(?i)does not exist|no such table"):
            await migrator.run([DropAbsentTable()])
    finally:
        await migrator.drop_all()
        await db.dispose()
