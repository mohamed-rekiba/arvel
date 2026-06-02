"""Add products_slug_en_unique index if it doesn't already exist.

Idempotent patch — the original 000003 migration creates this index on fresh
installs. This migration ensures the index exists on databases created before
that index was added.
"""

from __future__ import annotations

from arvel.database import Schema

_UP_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS products_slug_en_unique
    ON products ((slug->>'en'))
    WHERE deleted_at IS NULL;
"""

_DOWN_SQL = """
DROP INDEX IF EXISTS products_slug_en_unique;
"""


async def up(schema: Schema) -> None:
    schema.run_sql(_UP_SQL)


async def down(schema: Schema) -> None:
    schema.run_sql(_DOWN_SQL)
