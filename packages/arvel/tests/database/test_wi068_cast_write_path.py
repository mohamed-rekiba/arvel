"""WI-arvel-068 — Epic 049 Story 10 write-path follow-up.

Read-path casts shipped in WI-063 — ``m.field`` returns the cast value when
``__casts__`` lists the column. The follow-up is symmetric: assignment
(``m.field = raw_value``) and construction (``Model(field=raw_value)``)
should coerce eagerly so the **stored** value is already the right type
before SQLAlchemy persists it.

Tests bypass ``Model.__getattribute__`` via ``object.__getattribute__`` to
read the raw stored value — proves the coercion happened on write, not on
read. Invalid values raise ``CastError`` immediately at assignment, not on
the first read.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, ClassVar

import pytest
from arvel.database import Model
from arvel.database.exceptions import CastError
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class _Post(Model):
    __tablename__ = "wi068_posts"
    __casts__: ClassVar[dict[str, str]] = {
        "published_at": "datetime",
        "publish_on": "date",
        "epoch": "timestamp",
        "is_active": "boolean",
        "quantity": "int",
        "amount": "float",
        "code": "string",
    }
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    published_at: Mapped[Any] = mapped_column(String(80), default=None)
    publish_on: Mapped[Any] = mapped_column(String(80), default=None)
    epoch: Mapped[Any] = mapped_column(String(80), default=None)
    is_active: Mapped[Any] = mapped_column(String(80), default=None)
    quantity: Mapped[Any] = mapped_column(String(80), default=None)
    amount: Mapped[Any] = mapped_column(String(80), default=None)
    code: Mapped[Any] = mapped_column(String(80), default=None)
    title: Mapped[Any] = mapped_column(String(80), default=None)


def _raw(instance: Any, name: str) -> Any:
    """Read the underlying stored value, bypassing ``Model.__getattribute__``."""
    return object.__getattribute__(instance, name)


def _build(**kwargs: Any) -> _Post:
    return _Post(**kwargs)


class TestWritePathCoercion:
    def test_assignment_coerces_iso_string_to_datetime(self) -> None:
        m = _build()
        m.published_at = "2026-05-25T01:30:00Z"
        stored = _raw(m, "published_at")
        assert isinstance(stored, datetime)
        assert stored == datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)

    def test_assignment_coerces_epoch_to_datetime(self) -> None:
        m = _build()
        m.published_at = 1779672600
        stored = _raw(m, "published_at")
        assert isinstance(stored, datetime)

    def test_assignment_coerces_date_string(self) -> None:
        m = _build()
        m.publish_on = "2026-05-25"
        stored = _raw(m, "publish_on")
        assert isinstance(stored, date)
        assert not isinstance(stored, datetime)
        assert stored == date(2026, 5, 25)

    def test_assignment_coerces_string_to_timestamp_int(self) -> None:
        m = _build()
        m.epoch = "2026-05-25T01:30:00Z"
        stored = _raw(m, "epoch")
        assert isinstance(stored, int)
        assert not isinstance(stored, bool)
        assert stored == 1779672600

    def test_assignment_coerces_int_to_boolean(self) -> None:
        m = _build()
        m.is_active = 1
        assert _raw(m, "is_active") is True
        m.is_active = 0
        assert _raw(m, "is_active") is False

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("0", False, id="string-zero-false"),
            pytest.param("", False, id="empty-string-false"),
            pytest.param("1", True, id="string-one-true"),
            pytest.param("true", True, id="string-true-true"),
            # PHP's (bool)"false" is True — Laravel parity, not intuition.
            pytest.param("false", True, id="string-false-still-true"),
        ],
    )
    def test_boolean_cast_matches_php_bool_for_strings(self, raw: str, expected: bool) -> None:
        m = _build()
        m.is_active = raw
        assert _raw(m, "is_active") is expected

    def test_assignment_coerces_string_to_int(self) -> None:
        m = _build()
        m.quantity = "42"
        assert _raw(m, "quantity") == 42
        assert isinstance(_raw(m, "quantity"), int)

    def test_assignment_coerces_string_to_float(self) -> None:
        m = _build()
        m.amount = "10.5"
        stored = _raw(m, "amount")
        assert isinstance(stored, float)
        assert stored == 10.5

    def test_assignment_coerces_int_to_string(self) -> None:
        m = _build()
        m.code = 42
        assert _raw(m, "code") == "42"
        assert isinstance(_raw(m, "code"), str)

    def test_none_assignment_bypasses_cast(self) -> None:
        m = _build(published_at="2026-05-25T01:30:00Z")
        m.published_at = None
        assert _raw(m, "published_at") is None

    def test_non_cast_attribute_assignment_unchanged(self) -> None:
        m = _build()
        m.title = "Hello World"
        assert _raw(m, "title") == "Hello World"


class TestConstructionCoerces:
    def test_constructor_coerces_kwargs_through_casts(self) -> None:
        m = _build(
            published_at="2026-05-25T01:30:00Z",
            publish_on="2026-05-25",
            epoch="2026-05-25T01:30:00Z",
            quantity="7",
        )
        assert isinstance(_raw(m, "published_at"), datetime)
        assert isinstance(_raw(m, "publish_on"), date)
        assert _raw(m, "epoch") == 1779672600
        assert _raw(m, "quantity") == 7


class TestWritePathFailsFast:
    def test_invalid_datetime_raises_at_assignment(self) -> None:
        m = _build()
        with pytest.raises(CastError) as ei:
            m.published_at = "not a date"
        assert "datetime" in str(ei.value)

    def test_invalid_datetime_raises_at_construction(self) -> None:
        with pytest.raises(CastError):
            _build(published_at="not a date")

    def test_invalid_date_raises_at_assignment(self) -> None:
        m = _build()
        with pytest.raises(CastError):
            m.publish_on = "nope"

    def test_invalid_timestamp_raises_at_assignment(self) -> None:
        m = _build()
        with pytest.raises(CastError):
            m.epoch = "not an epoch"

    def test_bool_rejected_for_timestamp_at_write(self) -> None:
        # bool is an int subclass; refuse explicitly to avoid 0/1 becoming epoch 0/1.
        m = _build()
        with pytest.raises(CastError):
            m.epoch = True


class TestWriteReadSymmetry:
    """After a write, the read returns an equal value — no double coercion drift."""

    def test_datetime_round_trip(self) -> None:
        m = _build()
        m.published_at = "2026-05-25T01:30:00Z"
        stored = _raw(m, "published_at")
        assert isinstance(stored, datetime)
        assert m.published_at == stored

    def test_date_round_trip(self) -> None:
        m = _build()
        m.publish_on = "2026-05-25"
        stored = _raw(m, "publish_on")
        assert isinstance(stored, date)
        assert m.publish_on == stored

    def test_timestamp_round_trip(self) -> None:
        m = _build()
        m.epoch = "2026-05-25T01:30:00Z"
        assert m.epoch == _raw(m, "epoch") == 1779672600


class _ParentCasts(Model):
    __abstract__ = True
    __casts__: ClassVar[dict[str, str]] = {"flag": "boolean"}


class _ChildCasts(_ParentCasts):
    __tablename__ = "wi068_child_casts"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    flag: Mapped[Any] = mapped_column(String(80), default=None)


class TestInheritedCasts:
    def test_subclass_inherits_write_path_coercion(self) -> None:
        factory: Any = _ChildCasts
        m = factory(flag=1)
        assert object.__getattribute__(m, "flag") is True
