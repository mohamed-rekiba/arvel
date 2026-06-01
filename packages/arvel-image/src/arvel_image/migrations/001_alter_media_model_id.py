"""Alter media.model_id from INTEGER to VARCHAR(36).

Run this migration after upgrading to arvel-image a medialibrary parity release on an existing
database. New installs will have VARCHAR(36) from the create_media_table
migration directly.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from sqlalchemy import String

__tablename__ = "media"


async def up(schema: Schema) -> None:
    """Change model_id to VARCHAR(36)."""

    def _alter(t: Blueprint) -> None:
        t.modify_column("model_id", type_=String(36), nullable=False)

    schema.table(__tablename__, _alter)


async def down(schema: Schema) -> None:
    """Revert model_id to INTEGER.

    Data loss will occur for any rows where model_id contains a non-numeric
    UUID value.
    """
    from sqlalchemy import Integer  # noqa: PLC0415

    def _revert(t: Blueprint) -> None:
        t.modify_column("model_id", type_=Integer(), nullable=False)

    schema.table(__tablename__, _revert)
