"""Model — a declared-but-unset column reads as ``None`` (Laravel parity: ``$model->col`` is null), while
an unknown attribute still raises ``AttributeError`` (typo safety). Regression: a freshly *created*
model used to raise on a nullable column that wasn't provided (e.g. ``user.email_verified_at`` right
after ``create()``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver


class Widget(Model):
    __table_name__ = "widgets"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "note": str, "verified_at": datetime}
    __fillable__: ClassVar[list[str]] = ["name"]


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    Widget.set_connection(db)
    await db.execute(sa.schema.CreateTable(Widget.__table__))
    return db


async def test_unset_known_column_reads_as_none_after_create() -> None:
    db = await _db()
    try:
        widget = await Widget.create(name="a")  # `note` + `verified_at` not provided
        assert widget.note is None  # declared column, unset → None (was AttributeError)
        assert widget.verified_at is None
    finally:
        await db.dispose()


def test_unknown_attribute_still_raises() -> None:
    with pytest.raises(AttributeError):
        _ = Widget().totally_unknown_attr  # not a column → typo safety preserved


async def test_loaded_null_column_is_none() -> None:
    db = await _db()
    try:
        widget = await Widget.create(name="b")
        found = await Widget.find(widget.id)
        assert found is not None
        assert found.note is None  # loaded NULL column → None (already worked; guards the path)
    finally:
        await db.dispose()
