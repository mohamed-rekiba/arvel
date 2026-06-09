"""Arvon — fluent, immutable, timezone-aware datetime (Carbon parity).

Wraps the ``whenever`` library. Callers never touch ``whenever`` directly; this module
is the single seam, so the backing library can move without rippling outward. Every
``Arvon`` is timezone-aware and stored against UTC by default; transforms return new
instances.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, Final, Literal

import whenever as w
from pydantic_core import core_schema

if TYPE_CHECKING:
    from collections.abc import Generator

    from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
    from pydantic.json_schema import JsonSchemaValue
    from pydantic_core import CoreSchema

BoundaryUnit = Literal["day", "week", "month", "year"]

# An ISO-8601 datetime tops out well under this; anything longer is junk we won't parse.
_MAX_PARSE_LEN: Final = 64


class ArvonParseError(ValueError):
    """Raised when a value can't be turned into an Arvon. Message stays bounded."""


class Arvon:
    """A moment in time. Immutable; tz-aware; UTC by default."""

    __slots__ = ("_zdt",)

    _zdt: w.ZonedDateTime

    # Active time-travel patches (Carbon's setTestNow), unwound by travel_back().
    _patches: ClassVar[list[object]] = []

    def __init__(self, zdt: w.ZonedDateTime) -> None:
        object.__setattr__(self, "_zdt", zdt)

    # ── construction ────────────────────────────────────────────────────

    @classmethod
    def now(cls) -> Arvon:
        return cls(w.ZonedDateTime.now("UTC"))

    @classmethod
    def today(cls) -> Arvon:
        return cls.now().start_of("day")

    @classmethod
    def of(cls, year: int, month: int, day: int, *, tz: str = "UTC") -> Arvon:
        """Build a date at midnight. Chain ``.at(hour, minute, second)`` for a time."""
        try:
            return cls(w.ZonedDateTime(year, month, day, tz=tz))
        except (ValueError, w.TimeZoneNotFoundError) as exc:
            raise ArvonParseError(f"invalid date components for tz {tz!r}") from exc

    def at(self, hour: int, minute: int = 0, second: int = 0) -> Arvon:
        try:
            return Arvon(
                self._zdt.replace(
                    hour=hour, minute=minute, second=second, nanosecond=0, disambiguate="compatible"
                )
            )
        except ValueError as exc:
            raise ArvonParseError("invalid time components") from exc

    @classmethod
    def parse(cls, value: str) -> Arvon:
        if not value or len(value) > _MAX_PARSE_LEN or value.isspace():
            raise ArvonParseError("not a valid ISO-8601 datetime")
        try:
            return cls(w.Instant.parse_iso(value).to_tz("UTC"))
        except ValueError:
            pass
        try:
            return cls(w.PlainDateTime.parse_iso(value).assume_tz("UTC"))
        except (ValueError, w.TimeZoneNotFoundError) as exc:
            raise ArvonParseError("not a valid ISO-8601 datetime") from exc

    @classmethod
    def from_timestamp(cls, value: float) -> Arvon:
        try:
            return cls(w.Instant.from_timestamp(value).to_tz("UTC"))
        except (ValueError, OverflowError, OSError) as exc:
            raise ArvonParseError("timestamp out of range") from exc

    @classmethod
    def from_datetime(cls, value: datetime) -> Arvon:
        base = value if value.tzinfo is None else value.astimezone(UTC)
        return cls(
            w.ZonedDateTime(
                base.year,
                base.month,
                base.day,
                base.hour,
                base.minute,
                base.second,
                nanosecond=base.microsecond * 1000,
                tz="UTC",
            )
        )

    # ── arithmetic (immutable) ──────────────────────────────────────────

    def add_years(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(years=n))

    def add_months(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(months=n))

    def add_weeks(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(days=7 * n))

    def add_days(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(days=n))

    def add_hours(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(hours=n))

    def add_minutes(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(minutes=n))

    def add_seconds(self, n: int) -> Arvon:
        return Arvon(self._zdt.add(seconds=n))

    def sub_years(self, n: int) -> Arvon:
        return self.add_years(-n)

    def sub_months(self, n: int) -> Arvon:
        return self.add_months(-n)

    def sub_weeks(self, n: int) -> Arvon:
        return self.add_weeks(-n)

    def sub_days(self, n: int) -> Arvon:
        return self.add_days(-n)

    def sub_hours(self, n: int) -> Arvon:
        return self.add_hours(-n)

    def sub_minutes(self, n: int) -> Arvon:
        return self.add_minutes(-n)

    def sub_seconds(self, n: int) -> Arvon:
        return self.add_seconds(-n)

    # ── comparison ──────────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Arvon):
            return NotImplemented
        return self._zdt == other._zdt

    def __hash__(self) -> int:
        return hash(self._zdt)

    def __lt__(self, other: Arvon) -> bool:
        return self._zdt < other._zdt

    def __le__(self, other: Arvon) -> bool:
        return self._zdt <= other._zdt

    def __gt__(self, other: Arvon) -> bool:
        return self._zdt > other._zdt

    def __ge__(self, other: Arvon) -> bool:
        return self._zdt >= other._zdt

    def eq(self, other: Arvon) -> bool:
        return self == other

    def ne(self, other: Arvon) -> bool:
        return self != other

    def lt(self, other: Arvon) -> bool:
        return self < other

    def le(self, other: Arvon) -> bool:
        return self <= other

    def gt(self, other: Arvon) -> bool:
        return self > other

    def ge(self, other: Arvon) -> bool:
        return self >= other

    @property
    def is_past(self) -> bool:
        return self < Arvon.now()

    @property
    def is_future(self) -> bool:
        return self > Arvon.now()

    def between(self, start: Arvon, end: Arvon, *, inclusive: bool = True) -> bool:
        if inclusive:
            return start <= self <= end
        return start < self < end

    # ── boundaries ──────────────────────────────────────────────────────

    def start_of(self, unit: BoundaryUnit) -> Arvon:
        if unit == "week":
            weekday = self._zdt.to_instant().to_stdlib().weekday()  # Monday = 0
            return Arvon(self._zdt.start_of("day").subtract(days=weekday))
        return Arvon(self._zdt.start_of(unit))

    def end_of(self, unit: BoundaryUnit) -> Arvon:
        if unit == "week":
            weekday = self._zdt.to_instant().to_stdlib().weekday()  # Monday = 0
            start = self._zdt.start_of("day").subtract(days=weekday)
            return Arvon(start.add(days=6).end_of("day"))
        return Arvon(self._zdt.end_of(unit))

    # ── timezone ────────────────────────────────────────────────────────

    def in_timezone(self, tz: str) -> Arvon:
        return Arvon(self._zdt.to_tz(tz))

    # ── humanize ────────────────────────────────────────────────────────

    def diff_for_humans(self, other: Arvon | None = None) -> str:
        reference = other if other is not None else Arvon.now()
        delta = self.to_datetime().timestamp() - reference.to_datetime().timestamp()
        is_future = delta > 0
        seconds = int(abs(delta))
        count, unit = _largest_unit(seconds)
        plural = "" if count == 1 else "s"
        phrase = f"{count} {unit}{plural}"
        return f"in {phrase}" if is_future else f"{phrase} ago"

    # ── format / serialize / interop ────────────────────────────────────

    def to_iso8601(self) -> str:
        return self._zdt.to_instant().format_iso()

    def to_date_string(self) -> str:
        return f"{self._zdt.year:04d}-{self._zdt.month:02d}-{self._zdt.day:02d}"

    def format(self, pattern: str) -> str:
        return self._zdt.format(pattern)

    def to_datetime(self) -> datetime:
        return self._zdt.to_instant().to_stdlib()

    def __repr__(self) -> str:
        return f"Arvon({self.to_iso8601()})"

    def __str__(self) -> str:
        return self.to_iso8601()

    # ── test-time control (Carbon's setTestNow / travel) ────────────────

    @classmethod
    @contextmanager
    def freeze(cls, at: Arvon) -> Generator[None]:
        with w.patch_current_time(at._zdt.to_instant(), keep_ticking=False):
            yield

    @classmethod
    def travel(cls, to: Arvon) -> None:
        patch = w.patch_current_time(to._zdt.to_instant(), keep_ticking=False)
        patch.__enter__()
        cls._patches.append(patch)

    @classmethod
    def travel_back(cls) -> None:
        if cls._patches:
            patch = cls._patches.pop()
            # patch is a context manager from patch_current_time
            patch.__exit__(None, None, None)  # type: ignore[attr-defined]

    # ── pydantic integration ────────────────────────────────────────────

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        def _validate(value: object) -> Arvon:
            if isinstance(value, Arvon):
                return value
            if isinstance(value, str):
                return cls.parse(value)
            if isinstance(value, datetime):
                return cls.from_datetime(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return cls.from_timestamp(value)
            raise ValueError("expected an ISO-8601 string, timestamp, or datetime")

        def _serialize(value: Arvon) -> str:
            return value.to_iso8601()

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _serialize, when_used="json", return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string", "format": "date-time"}


def _largest_unit(seconds: int) -> tuple[int, str]:
    for size, name in _UNITS:
        if seconds >= size:
            return max(seconds // size, 1), name
    return max(seconds, 0), "second"


_UNITS: Final[tuple[tuple[int, str], ...]] = (
    (31_536_000, "year"),
    (2_592_000, "month"),
    (604_800, "week"),
    (86_400, "day"),
    (3_600, "hour"),
    (60, "minute"),
    (1, "second"),
)


def now() -> Arvon:
    return Arvon.now()


def today() -> Arvon:
    return Arvon.today()
