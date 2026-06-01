"""Enum + extended built-in casts.

Laravel's ``$casts`` supports backed enums, ``object``, ``collection``, and
``datetime:FORMAT``. This covers the Arvel equivalents:

- An ``Enum`` subclass as the cast spec → read returns a member, write/serialize
  store the backing value.
- ``object`` → JSON decoded into an attribute-accessible namespace (read-only on
  write, like ``array``).
- ``collection`` → JSON decoded into an Arvel ``Collection``.
- ``datetime:FORMAT`` → read coerces to ``datetime``, serialize emits
  ``strftime(FORMAT)``.

Reads bypass ``Model.__getattribute__`` via ``object.__getattribute__`` to
assert the stored (write-path) value where it matters."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from arvel.database import Model, column, id_
from arvel.support.collections import Collection
from sqlalchemy import Integer, String


class Status(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Priority(Enum):
    LOW = 1
    HIGH = 2


class _Article(Model):
    __tablename__ = "wi017_articles"
    __casts__: ClassVar[dict[str, Any]] = {
        "status": Status,
        "priority": Priority,
        "meta": "object",
        "tags": "collection",
        "scheduled_at": "datetime:%Y-%m-%d %H:%M",
    }
    id: int = id_()
    status: Any = column(String(40), nullable=True, default=None)
    priority: Any = column(Integer, nullable=True, default=None)
    meta: Any = column(String(255), nullable=True, default=None)
    tags: Any = column(String(255), nullable=True, default=None)
    scheduled_at: Any = column(String(40), nullable=True, default=None)


def _raw(instance: Any, name: str) -> Any:
    return object.__getattribute__(instance, name)


class TestEnumCast:
    def test_read_returns_member_from_backing_value(self) -> None:
        a = _Article()
        object.__setattr__(a, "status", "published")
        assert a.status is Status.PUBLISHED

    def test_write_stores_backing_value_from_member(self) -> None:
        a = _Article(status=Status.DRAFT)
        assert _raw(a, "status") == "draft"
        assert a.status is Status.DRAFT

    def test_write_accepts_raw_backing_value(self) -> None:
        a = _Article(status="published")
        assert _raw(a, "status") == "published"
        assert a.status is Status.PUBLISHED

    def test_int_backed_enum_round_trips(self) -> None:
        a = _Article(priority=Priority.HIGH)
        assert _raw(a, "priority") == 2
        assert a.priority is Priority.HIGH

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError, match="nonsense"):
            _Article(status="nonsense")

    def test_serialize_emits_backing_value(self) -> None:
        a = _Article(status=Status.PUBLISHED, priority=Priority.LOW)
        data = a.to_dict()
        assert data["status"] == "published"
        assert data["priority"] == 1


class TestObjectCast:
    def test_read_decodes_json_to_namespace(self) -> None:
        a = _Article()
        object.__setattr__(a, "meta", '{"views": 10, "author": "kira"}')
        meta = a.meta
        assert isinstance(meta, SimpleNamespace)
        assert meta.views == 10
        assert meta.author == "kira"

    def test_write_is_read_only_skip(self) -> None:
        # collection/object casts skip write coercion, like ``array``.
        a = _Article(meta='{"k": 1}')
        assert _raw(a, "meta") == '{"k": 1}'

    def test_serialize_emits_plain_dict(self) -> None:
        a = _Article(meta='{"views": 10}')
        assert a.to_dict()["meta"] == {"views": 10}


class TestCollectionCast:
    def test_read_decodes_json_array_to_collection(self) -> None:
        a = _Article()
        object.__setattr__(a, "tags", '["python", "laravel"]')
        tags = cast("Collection[str]", a.tags)
        assert isinstance(tags, Collection)
        assert list(tags) == ["python", "laravel"]

    def test_read_handles_python_list(self) -> None:
        a = _Article()
        object.__setattr__(a, "tags", ["a", "b"])
        assert isinstance(a.tags, Collection)

    def test_serialize_emits_plain_list(self) -> None:
        a = _Article(tags='["x", "y"]')
        assert a.to_dict()["tags"] == ["x", "y"]


class TestDatetimeFormatCast:
    def test_read_coerces_formatted_string(self) -> None:
        a = _Article()
        object.__setattr__(a, "scheduled_at", "2026-05-30 14:45")
        dt = a.scheduled_at
        assert isinstance(dt, datetime)
        assert dt == datetime(2026, 5, 30, 14, 45, tzinfo=UTC)

    def test_read_falls_back_to_iso(self) -> None:
        a = _Article()
        object.__setattr__(a, "scheduled_at", "2026-05-30T14:45:00Z")
        assert isinstance(a.scheduled_at, datetime)

    def test_serialize_emits_formatted_string(self) -> None:
        a = _Article(scheduled_at="2026-05-30T14:45:00Z")
        assert a.to_dict()["scheduled_at"] == "2026-05-30 14:45"
