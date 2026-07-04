"""arvel.dates — ``Date`` over **whenever** (Carbon parity).

The value behind a ``Date`` is a whenever ``ZonedDateTime`` — never stdlib
``datetime`` — so DST/naive-vs-aware footguns are gone (G4 stack fidelity).
whenever is a light **core** dep, imported at module top. Grounded in
knowledge/port/14-dates.md.
"""

from __future__ import annotations

import contextvars
from typing import Any

from whenever import (
    FRIDAY,
    MONDAY,
    SATURDAY,
    SUNDAY,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    Instant,
    ZonedDateTime,
)

# Weekend days aren't universally Sat/Sun (e.g. Egypt/Gulf rest Fri/Sat), so is_weekend
# reads config('app.weekend_days') and only falls back to Sat/Sun.
_WEEKDAYS = {
    "monday": MONDAY,
    "tuesday": TUESDAY,
    "wednesday": WEDNESDAY,
    "thursday": THURSDAY,
    "friday": FRIDAY,
    "saturday": SATURDAY,
    "sunday": SUNDAY,
}
_DEFAULT_WEEKEND = (SATURDAY, SUNDAY)


def _weekend_days() -> tuple[Any, ...]:
    """The configured weekend weekdays (``config('app.weekend_days')`` as day names), or Sat/Sun."""
    from arvel.kernel.globals import app, has_application

    names = app().config("app.weekend_days", None) if has_application() else None
    if not names:
        return _DEFAULT_WEEKEND
    resolved = tuple(
        _WEEKDAYS[key] for name in names if (key := str(name).strip().lower()) in _WEEKDAYS
    )
    return resolved or _DEFAULT_WEEKEND


_test_now: contextvars.ContextVar[ZonedDateTime | None] = contextvars.ContextVar(
    "arvel_test_now", default=None
)


def _app_timezone() -> str:
    from arvel.kernel.globals import app, has_application

    if has_application():
        return str(app().config("app.timezone", "UTC") or "UTC")
    return "UTC"


class Date:
    """An immutable, timezone-aware datetime backed by whenever."""

    def __init__(self, dt: ZonedDateTime) -> None:
        self._dt = dt

    @classmethod
    def now(cls, tz: str | None = None) -> Date:
        frozen = _test_now.get()
        if frozen is not None:
            return cls(frozen if tz is None else frozen.to_tz(tz))
        return cls(ZonedDateTime.now(tz or _app_timezone()))

    @classmethod
    def today(cls, tz: str | None = None) -> Date:
        return cls.now(tz).start_of_day()

    @classmethod
    def parse(cls, value: str | Date, tz: str | None = None) -> Date:
        if isinstance(value, Date):
            return value
        dt = ZonedDateTime.parse_iso(str(value))
        return cls(dt if tz is None else dt.to_tz(tz))

    @classmethod
    def from_py(cls, value: Any, tz: str | None = None) -> Date:
        """Wrap a stdlib ``datetime`` (e.g. a value a DateTime DB column hydrates to) in a Date.
        A naive datetime is assumed to be in ``tz`` (the app timezone by default); an aware one is
        converted to it. Falls back to ISO-string parsing, so a SQLite-stored ISO string still
        reads back as a Date."""
        import datetime as _datetime

        if isinstance(value, Date):
            return value
        zone = tz or _app_timezone()
        if isinstance(value, _datetime.datetime):
            if value.tzinfo is None:
                from zoneinfo import ZoneInfo

                value = value.replace(tzinfo=ZoneInfo(zone))
            return cls(Instant.from_timestamp(value.timestamp()).to_tz(zone))
        return cls.parse(value, tz)

    def add(self, **units: int) -> Date:
        # whenever's add() overloads are keyword-only-by-name; **dict is fine at runtime.
        dt: Any = self._dt
        return Date(dt.add(**units))

    def subtract(self, **units: int) -> Date:
        negated = {unit: -amount for unit, amount in units.items()}
        dt: Any = self._dt
        return Date(dt.add(**negated))

    def add_days(self, n: int) -> Date:
        return Date(self._dt.add(days=n))

    def start_of_day(self) -> Date:
        return Date(self._dt.start_of("day"))

    def is_weekend(self) -> bool:
        """Whether this date falls on a weekend — per ``config('app.weekend_days')`` (day names),
        defaulting to Saturday/Sunday. Carbon parity (weekend days are region-specific)."""
        return self._dt.date().day_of_week() in _weekend_days()

    def is_weekday(self) -> bool:
        """The inverse of :meth:`is_weekend` — a working day under the configured weekend."""
        return not self.is_weekend()

    def to_iso(self) -> str:
        return self._dt.format_iso()

    def to_py(self) -> Any:
        return self._dt.to_stdlib()

    @property
    def raw(self) -> ZonedDateTime:
        return self._dt

    @staticmethod
    def _locale(locale: str | None) -> str:
        if locale is not None:
            return locale
        from arvel.localization import current_locale

        return current_locale.get()

    def format(self, fmt: str = "medium", locale: str | None = None) -> str:
        """Locale-aware datetime formatting via Babel (the ``[i18n]`` tier). ``fmt`` is a CLDR
        preset (``short``/``medium``/``long``/``full``) or a Babel pattern; ``locale`` defaults
        to the current request locale."""
        from babel.dates import format_datetime

        return format_datetime(self.to_py(), format=fmt, locale=self._locale(locale))

    def format_date(self, fmt: str = "medium", locale: str | None = None) -> str:
        """Locale-aware date-only formatting via Babel (``[i18n]``)."""
        from babel.dates import format_date

        return format_date(self.to_py(), format=fmt, locale=self._locale(locale))

    def format_time(self, fmt: str = "medium", locale: str | None = None) -> str:
        """Locale-aware time-only formatting via Babel (``[i18n]``)."""
        from babel.dates import format_time

        return format_time(self.to_py(), format=fmt, locale=self._locale(locale))

    # (unit, seconds) from largest to smallest — month≈30d, year≈365d (Carbon's approximations).
    _HUMAN_UNITS = (
        ("year", 31_536_000),
        ("month", 2_592_000),
        ("week", 604_800),
        ("day", 86_400),
        ("hour", 3_600),
        ("minute", 60),
        ("second", 1),
    )

    def diff_for_humans(self, other: Date | None = None) -> str:
        """A relative phrase vs ``other`` (or now): ``in 3 hours`` / ``2 days ago`` / ``just now``.
        Covers seconds→years; pluralizes; ``in`` for the future, ``ago`` for the past."""
        reference = (other if other is not None else Date.now(self._dt.tz)).to_py()
        seconds = (self.to_py() - reference).total_seconds()
        future = seconds >= 0
        seconds = abs(seconds)
        for unit, size in self._HUMAN_UNITS:
            if seconds >= size:
                amount = int(seconds // size)
                phrase = f"{amount} {unit}{'s' if amount != 1 else ''}"
                return f"in {phrase}" if future else f"{phrase} ago"
        return "just now"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Date) and self._dt == other._dt

    def __hash__(self) -> int:
        return hash(self._dt)

    # Non-Date operands return NotImplemented so Python raises TypeError instead of AttributeError.
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Date):
            return NotImplemented
        return self._dt < other._dt

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Date):
            return NotImplemented
        return self._dt <= other._dt

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Date):
            return NotImplemented
        return self._dt > other._dt

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Date):
            return NotImplemented
        return self._dt >= other._dt

    def __repr__(self) -> str:
        return f"Date({self._dt.format_iso()})"

    @classmethod
    def set_test_now(cls, value: Date | None) -> None:
        _test_now.set(value._dt if value is not None else None)

    @classmethod
    def test_now(cls) -> Date | None:
        """The currently frozen test ``Date`` (or ``None`` when time isn't frozen)."""
        raw = _test_now.get()
        return cls(raw) if raw is not None else None


def now(tz: str | None = None) -> Date:
    return Date.now(tz)


def today(tz: str | None = None) -> Date:
    return Date.today(tz)


__all__ = ["Date", "now", "today"]
