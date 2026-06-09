"""Opt-in `arvon` ORM cast — model datetime/date columns return Arvon (UTC-coerced)."""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, column, id_
from arvel.support.arvon import Arvon
from sqlalchemy import String


class Event(Model):
    __tablename__ = "arvon_cast_events"
    __casts__: ClassVar[dict[str, Any]] = {"happened_at": "arvon"}

    id: int = id_()
    happened_at: Any = column(String(64), default="")


def test_arvon_cast_returns_arvon_from_iso_string() -> None:
    e = Event(happened_at="2026-06-15T12:30:00Z")
    assert isinstance(e.happened_at, Arvon)
    assert e.happened_at == Arvon.of(2026, 6, 15).at(12, 30, 0)


def test_arvon_cast_coerces_naive_to_utc() -> None:
    e = Event(happened_at="2026-06-15T12:30:00")
    assert e.happened_at == Arvon.of(2026, 6, 15).at(12, 30, 0)


def test_arvon_cast_serializes_to_iso() -> None:
    e = Event(happened_at=Arvon.of(2026, 6, 15).at(12, 30, 0))
    assert e.to_dict()["happened_at"] == "2026-06-15T12:30:00Z"
