"""WI-arvel-063 — Epic 049 Story 10: `datetime` / `date` / `timestamp` casts.

`__casts__` already handles bool/int/float/str/dict/list. The Laravel-parity
gap is the temporal trio:

- ``datetime`` — accept ISO-8601 strings, epoch seconds (int/float), and bare
  ``datetime`` instances; output a tz-aware ``datetime`` in UTC.
- ``date`` — accept ISO ``YYYY-MM-DD`` strings, ``datetime``/``date``
  instances, and epoch seconds; output a ``date`` (no time component).
- ``timestamp`` — accept the same inputs and output an ``int`` epoch in
  seconds (UTC).

A bad cast input raises ``CastError`` (subclass of ``ORMError``) — same
exception hierarchy as the rest of the ORM so the HTTP layer can translate
it via the exception-translator registry if a caller wants 400 instead of 500.

Tests go through the public surface: define a tiny ``Model`` subclass with
``__casts__`` set, construct an instance with the raw value, then read the
attribute and assert the cast result. No private symbol access.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timezone
from typing import Any, ClassVar

import pytest
from arvel.database import Model
from arvel.database.exceptions import CastError, ORMError
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class _DatetimeModel(Model):
    __tablename__ = "wi063_datetime"
    __casts__: ClassVar[dict[str, str]] = {"field": "datetime"}
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    field: Mapped[Any] = mapped_column(String(80), default=None)


class _DateModel(Model):
    __tablename__ = "wi063_date"
    __casts__: ClassVar[dict[str, str]] = {"field": "date"}
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    field: Mapped[Any] = mapped_column(String(80), default=None)


class _TimestampModel(Model):
    __tablename__ = "wi063_timestamp"
    __casts__: ClassVar[dict[str, str]] = {"field": "timestamp"}
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    field: Mapped[Any] = mapped_column(String(80), default=None)


def _build(model_cls: type[Model], value: object) -> Any:
    """Build an instance with ``value`` pre-set via the dataclass constructor.

    Pyright's reading of ``MappedAsDataclass``-generated ``__init__`` is
    incomplete and trips ``reportCallIssue`` on ``Model(value=...)`` even
    though the runtime accepts it cleanly. Calling through ``Any`` widens
    the type at the call site so pyright stops complaining while preserving
    runtime SA instrumentation.
    """
    factory: Any = model_cls
    return factory(field=value)


class TestDatetimeCast:
    M: ClassVar[type[Model]] = _DatetimeModel

    def test_isoformat_string_to_datetime(self) -> None:
        m = _build(self.M, "2026-05-25T01:30:00Z")
        result = m.field
        assert isinstance(result, datetime)
        assert result == datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)
        assert result.tzinfo is not None

    def test_isoformat_with_offset_normalised_to_utc(self) -> None:
        m = _build(self.M, "2026-05-25T04:30:00+03:00")
        assert m.field == datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)
        assert m.field.tzinfo == UTC

    def test_epoch_int_to_datetime(self) -> None:
        # 2026-05-25T01:30:00Z = 1779672600
        m = _build(self.M, 1779672600)
        assert m.field == datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)

    def test_epoch_float_to_datetime(self) -> None:
        m = _build(self.M, 1779672600.5)
        assert isinstance(m.field, datetime)
        assert m.field.microsecond == 500_000

    def test_datetime_already_tz_aware_passthrough(self) -> None:
        dt = datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)
        m = _build(self.M, dt)
        assert m.field == dt
        assert m.field.tzinfo == UTC

    def test_naive_datetime_assumed_utc(self) -> None:
        dt = datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC).replace(tzinfo=None)
        m = _build(self.M, dt)
        assert m.field == datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)
        assert m.field.tzinfo == UTC

    def test_non_utc_aware_datetime_converted_to_utc(self) -> None:
        from datetime import timedelta

        plus3 = timezone(timedelta(hours=3))
        dt = datetime(2026, 5, 25, 4, 30, 0, tzinfo=plus3)
        m = _build(self.M, dt)
        assert m.field == datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)

    def test_invalid_string_raises_cast_error(self) -> None:
        # WI-068 made coercion fail-fast at write — bad input never reaches storage.
        with pytest.raises(CastError) as ei:
            _build(self.M, "not a date")
        assert "datetime" in str(ei.value)
        assert isinstance(ei.value, ORMError)

    def test_invalid_type_raises_cast_error(self) -> None:
        with pytest.raises(CastError):
            _build(self.M, [1, 2, 3])


class TestDateCast:
    M: ClassVar[type[Model]] = _DateModel

    def test_iso_string_to_date(self) -> None:
        m = _build(self.M, "2026-05-25")
        assert m.field == date(2026, 5, 25)

    def test_isoformat_with_time_truncated_to_date(self) -> None:
        m = _build(self.M, "2026-05-25T15:30:00Z")
        assert m.field == date(2026, 5, 25)
        assert isinstance(m.field, date)
        assert not isinstance(m.field, datetime)

    def test_datetime_to_date_uses_utc_calendar_day(self) -> None:
        dt = datetime(2026, 5, 25, 23, 30, 0, tzinfo=UTC)
        m = _build(self.M, dt)
        assert m.field == date(2026, 5, 25)

    def test_date_instance_passthrough(self) -> None:
        d = date(2026, 5, 25)
        m = _build(self.M, d)
        assert m.field == d

    def test_epoch_int_to_date(self) -> None:
        m = _build(self.M, 1779672600)
        assert m.field == date(2026, 5, 25)

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(CastError):
            _build(self.M, "nope")


class TestTimestampCast:
    M: ClassVar[type[Model]] = _TimestampModel

    def test_iso_string_to_epoch(self) -> None:
        m = _build(self.M, "2026-05-25T01:30:00Z")
        assert m.field == 1779672600

    def test_datetime_to_epoch(self) -> None:
        dt = datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC)
        m = _build(self.M, dt)
        assert m.field == 1779672600

    def test_naive_datetime_assumed_utc_for_timestamp(self) -> None:
        dt = datetime(2026, 5, 25, 1, 30, 0, tzinfo=UTC).replace(tzinfo=None)
        m = _build(self.M, dt)
        assert m.field == 1779672600

    def test_epoch_int_passthrough(self) -> None:
        m = _build(self.M, 1779672600)
        assert m.field == 1779672600

    def test_epoch_float_truncated_to_int(self) -> None:
        m = _build(self.M, 1779672600.9)
        assert m.field == 1779672600

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(CastError):
            _build(self.M, "invalid")


class TestCastErrorContract:
    """``CastError`` is a public, ORMError-derived exception."""

    def test_cast_error_is_orm_error(self) -> None:
        from arvel.database.exceptions import CastError as Imported

        assert Imported is CastError
        assert issubclass(Imported, ORMError)

    def test_cast_error_message_shape(self) -> None:
        err = CastError("datetime", "garbage", "ISO parse failed")
        assert "garbage" in str(err)
        assert "datetime" in str(err)
        assert err.cast_type == "datetime"
        assert err.value == "garbage"
