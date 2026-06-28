"""Advanced DB (doc 08) — Alembic-driven migrations (upgrade + downgrade). Test-first.

This is doc 08's mandated acceptance check: migrations run through Alembic Operations
(create_table/drop_table), not a raw-SQL migrator.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from arvel.database import ConnectionResolver
from arvel.database.migrations import Migration, Migrator


class CreatePosts(Migration):
    def up(self, schema: object) -> None:
        schema.create(  # type: ignore[attr-defined]
            "posts", lambda t: [t.id(), t.string("title"), t.boolean("published"), t.timestamps()]
        )

    def down(self, schema: object) -> None:
        schema.drop("posts")  # type: ignore[attr-defined]


async def test_migration_upgrade_then_downgrade() -> None:
    db = ConnectionResolver()
    migrator = Migrator(db)
    try:
        await migrator.run([CreatePosts()])
        # table exists → insert + read work
        await db.statement("INSERT INTO posts (title, published) VALUES ('hello', 1)")
        rows = await db.select("SELECT title FROM posts")
        assert rows[0]["title"] == "hello"

        await migrator.rollback([CreatePosts()])
        # table dropped → querying it now errors
        with pytest.raises(OperationalError):
            await db.select("SELECT * FROM posts")
    finally:
        await db.dispose()
