"""arvel.support.Arvon — fluent datetime (Carbon parity).

QA-Pre suite: these assert the PRD acceptance criteria. They fail until Arvon is
implemented (Red), then drive the implementation (Green).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from arvel.support.arvon import Arvon, ArvonParseError


@pytest.fixture
def frozen() -> object:
    """Freeze the clock at a fixed UTC instant for deterministic now()/today()."""
    at = Arvon.of(2026, 6, 15).at(12, 30, 0)
    with Arvon.freeze(at):
        yield at


class TestConstruction:
    def test_now_returns_arvon(self) -> None:
        assert isinstance(Arvon.now(), Arvon)

    def test_now_is_frozen_value(self, frozen: Arvon) -> None:
        assert Arvon.now() == frozen

    def test_today_is_start_of_day(self, frozen: Arvon) -> None:
        today = Arvon.today()
        assert today.to_date_string() == "2026-06-15"
        assert today == Arvon.of(2026, 6, 15)

    def test_of_builds_valid_instance(self) -> None:
        d = Arvon.of(2026, 1, 31).at(9, 15, 0)
        assert d.to_iso8601() == "2026-01-31T09:15:00Z"

    def test_of_rejects_impossible_date(self) -> None:
        with pytest.raises(ArvonParseError):
            Arvon.of(2026, 2, 30)


class TestParsing:
    def test_parse_iso8601(self) -> None:
        d = Arvon.parse("2026-06-15T12:30:00Z")
        assert d == Arvon.of(2026, 6, 15).at(12, 30, 0)

    def test_from_timestamp(self) -> None:
        d = Arvon.from_timestamp(0)
        assert d == Arvon.of(1970, 1, 1)

    def test_from_naive_datetime_is_utc(self) -> None:
        d = Arvon.from_datetime(datetime(2026, 6, 15, 12, 30, 0))  # noqa: DTZ001 — intentional naive input
        assert d == Arvon.of(2026, 6, 15).at(12, 30, 0)

    def test_from_aware_datetime(self) -> None:
        d = Arvon.from_datetime(datetime(2026, 6, 15, 12, 30, 0, tzinfo=UTC))
        assert d == Arvon.of(2026, 6, 15).at(12, 30, 0)

    @pytest.mark.parametrize("bad", ["", "not-a-date", "2026-13-99", "   "])
    def test_parse_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(ArvonParseError):
            Arvon.parse(bad)

    def test_parse_error_does_not_echo_full_input(self) -> None:
        huge = "x" * 10_000
        with pytest.raises(ArvonParseError) as exc:
            Arvon.parse(huge)
        # message must stay bounded — no echoing a 10k-char payload
        assert len(str(exc.value)) < 200


class TestArithmetic:
    def test_add_days_is_immutable(self) -> None:
        base = Arvon.of(2026, 6, 15)
        later = base.add_days(3)
        assert later == Arvon.of(2026, 6, 18)
        assert base == Arvon.of(2026, 6, 15)  # unchanged

    def test_sub_hours(self) -> None:
        assert Arvon.of(2026, 6, 15).at(12).sub_hours(2) == Arvon.of(2026, 6, 15).at(10)

    def test_add_months_clamps_to_last_valid_day(self) -> None:
        # Jan 31 + 1 month → Feb 28 (2026 is not a leap year)
        assert Arvon.of(2026, 1, 31).add_months(1) == Arvon.of(2026, 2, 28)

    def test_add_years(self) -> None:
        assert Arvon.of(2026, 6, 15).add_years(2) == Arvon.of(2028, 6, 15)


class TestComparison:
    def test_ordering(self) -> None:
        a = Arvon.of(2026, 1, 1)
        b = Arvon.of(2026, 1, 2)
        assert a < b and b > a and a != b
        assert a.lt(b) and b.gt(a) and a.eq(Arvon.of(2026, 1, 1))

    def test_is_past_and_future(self, frozen: Arvon) -> None:
        assert Arvon.of(2020, 1, 1).is_past
        assert Arvon.of(2030, 1, 1).is_future

    def test_between(self) -> None:
        mid = Arvon.of(2026, 6, 15)
        assert mid.between(Arvon.of(2026, 6, 1), Arvon.of(2026, 6, 30))
        assert not mid.between(Arvon.of(2026, 7, 1), Arvon.of(2026, 7, 30))

    def test_min_max_use_ordering(self) -> None:
        a = Arvon.of(2026, 1, 1)
        b = Arvon.of(2026, 6, 15)
        c = Arvon.of(2026, 12, 31)
        assert min(b, a, c) == a
        assert max(b, a, c) == c


class TestBoundaries:
    def test_start_of_day(self) -> None:
        assert Arvon.of(2026, 6, 15).at(13, 45, 9).start_of("day") == Arvon.of(2026, 6, 15)

    def test_end_of_month(self) -> None:
        assert Arvon.of(2026, 2, 10).end_of("month").to_date_string() == "2026-02-28"

    def test_start_of_year(self) -> None:
        assert Arvon.of(2026, 6, 15).start_of("year") == Arvon.of(2026, 1, 1)

    def test_start_of_week_is_monday(self) -> None:
        # 2026-06-15 is a Monday; 2026-06-17 (Wed) starts the same week.
        assert Arvon.of(2026, 6, 17).start_of("week") == Arvon.of(2026, 6, 15)

    def test_end_of_week_is_sunday(self) -> None:
        assert Arvon.of(2026, 6, 17).end_of("week").to_date_string() == "2026-06-21"


class TestTimezone:
    def test_in_timezone_preserves_instant(self) -> None:
        utc = Arvon.of(2026, 6, 15).at(12, 0, 0)
        ny = utc.in_timezone("America/New_York")
        # same instant, equal under instant comparison
        assert ny == utc
        # rendered local date string still the same calendar instant in iso
        assert utc.to_iso8601() == "2026-06-15T12:00:00Z"


class TestHumanize:
    def test_past_reads_ago(self, frozen: Arvon) -> None:
        phrase = Arvon.now().sub_hours(3).diff_for_humans()
        assert "ago" in phrase and "hour" in phrase

    def test_future_reads_in(self, frozen: Arvon) -> None:
        phrase = Arvon.now().add_days(2).diff_for_humans()
        assert phrase.startswith("in ") and "day" in phrase


class TestFormat:
    def test_to_iso8601(self) -> None:
        assert Arvon.of(2026, 6, 15).at(12, 30, 0).to_iso8601() == "2026-06-15T12:30:00Z"

    def test_to_date_string(self) -> None:
        assert Arvon.of(2026, 6, 15).to_date_string() == "2026-06-15"

    def test_format_custom_pattern(self) -> None:
        assert (
            Arvon.of(2026, 6, 15).at(9, 5, 3).format("YYYY-MM-DD hh:mm:ss") == "2026-06-15 09:05:03"
        )

    def test_to_datetime_is_aware_utc(self) -> None:
        dt = Arvon.of(2026, 6, 15).at(12, 30, 0).to_datetime()
        assert dt == datetime(2026, 6, 15, 12, 30, 0, tzinfo=UTC)
        assert dt.tzinfo is not None


class TestFreezeTravel:
    def test_travel_and_back(self) -> None:
        target = Arvon.of(2000, 1, 1)
        Arvon.travel(target)
        try:
            assert Arvon.now() == target
        finally:
            Arvon.travel_back()
        # after travel_back, now() is live again (not the frozen target)
        assert Arvon.now() != target

    def test_freeze_context_releases(self) -> None:
        at = Arvon.of(2010, 5, 5)
        with Arvon.freeze(at):
            assert Arvon.now() == at
        assert Arvon.now() != at


class TestHelpers:
    def test_now_helper(self, frozen: Arvon) -> None:
        from arvel.support import now

        assert now() == frozen

    def test_today_helper(self, frozen: Arvon) -> None:
        from arvel.support import today

        assert today() == Arvon.of(2026, 6, 15)


class TestPydantic:
    def test_field_accepts_iso_string(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            at: Arvon

        assert M.model_validate({"at": "2026-06-15T12:30:00Z"}).at == Arvon.of(2026, 6, 15).at(
            12, 30, 0
        )

    def test_field_accepts_timestamp(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            at: Arvon

        assert M.model_validate({"at": 0}).at == Arvon.of(1970, 1, 1)

    def test_field_serializes_to_iso(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            at: Arvon

        m = M(at=Arvon.of(2026, 6, 15).at(12, 30, 0))
        assert m.model_dump(mode="json")["at"] == "2026-06-15T12:30:00Z"

    def test_field_rejects_garbage(self) -> None:
        from pydantic import BaseModel, ValidationError

        class M(BaseModel):
            at: Arvon

        with pytest.raises(ValidationError):
            M.model_validate({"at": "garbage"})

    def test_json_schema_is_date_time_string(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            at: Arvon

        schema = M.model_json_schema()
        prop = schema["properties"]["at"]
        assert prop["type"] == "string"
        assert prop["format"] == "date-time"


class TestArithmeticCoverage:
    def test_all_add_units(self) -> None:
        base = Arvon.of(2026, 1, 1).at(0, 0, 0)
        assert base.add_years(1) == Arvon.of(2027, 1, 1)
        assert base.add_months(2) == Arvon.of(2026, 3, 1)
        assert base.add_weeks(1) == Arvon.of(2026, 1, 8)
        assert base.add_days(1) == Arvon.of(2026, 1, 2)
        assert base.add_hours(1) == base.at(1, 0, 0)
        assert base.add_minutes(1) == base.at(0, 1, 0)
        assert base.add_seconds(1) == base.at(0, 0, 1)

    def test_all_sub_units(self) -> None:
        base = Arvon.of(2026, 3, 8).at(2, 2, 2)
        assert base.sub_years(1) == Arvon.of(2025, 3, 8).at(2, 2, 2)
        assert base.sub_months(1) == Arvon.of(2026, 2, 8).at(2, 2, 2)
        assert base.sub_weeks(1) == Arvon.of(2026, 3, 1).at(2, 2, 2)
        assert base.sub_days(1) == Arvon.of(2026, 3, 7).at(2, 2, 2)
        assert base.sub_minutes(2) == base.at(2, 0, 2)
        assert base.sub_seconds(2) == base.at(2, 2, 0)


class TestComparisonCoverage:
    def test_aliases_and_dunders(self) -> None:
        a = Arvon.of(2026, 1, 1)
        b = Arvon.of(2026, 1, 2)
        assert a.ne(b) and b.ge(a) and a.le(b)
        assert (a <= b) and (b >= a)
        assert a != "not-an-arvon"
        assert hash(a) == hash(Arvon.of(2026, 1, 1))

    def test_repr_and_str(self) -> None:
        a = Arvon.of(2026, 6, 15).at(12, 30, 0)
        assert str(a) == "2026-06-15T12:30:00Z"
        assert repr(a) == "Arvon(2026-06-15T12:30:00Z)"


class TestErrorPaths:
    def test_at_rejects_invalid_time(self) -> None:
        with pytest.raises(ArvonParseError):
            Arvon.of(2026, 6, 15).at(25, 0, 0)

    def test_from_timestamp_out_of_range(self) -> None:
        with pytest.raises(ArvonParseError):
            Arvon.from_timestamp(1e30)

    def test_travel_back_with_no_patch_is_noop(self) -> None:
        # Stack is empty here; calling travel_back must not raise.
        Arvon.travel_back()


class TestHumanizeCoverage:
    def test_seconds_phrase(self, frozen: Arvon) -> None:
        assert Arvon.now().add_seconds(5).diff_for_humans() == "in 5 seconds"
        assert Arvon.now().sub_seconds(1).diff_for_humans() == "1 second ago"

    def test_explicit_reference(self) -> None:
        ref = Arvon.of(2026, 6, 15).at(12, 0, 0)
        later = ref.add_hours(3)
        assert later.diff_for_humans(ref) == "in 3 hours"


class TestPydanticCoverage:
    def test_accepts_arvon_passthrough(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            at: Arvon

        value = Arvon.of(2026, 6, 15)
        assert M(at=value).at == value

    def test_accepts_datetime(self) -> None:
        from pydantic import BaseModel

        class M(BaseModel):
            at: Arvon

        assert M.model_validate({"at": datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)}).at == Arvon.of(
            2026, 6, 15
        ).at(12, 0, 0)

    def test_rejects_unsupported_type(self) -> None:
        from pydantic import BaseModel, ValidationError

        class M(BaseModel):
            at: Arvon

        with pytest.raises(ValidationError):
            M.model_validate({"at": object()})
