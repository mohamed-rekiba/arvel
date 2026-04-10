"""Tests for ScheduleEntry — fluent API, cron parsing, due-time evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arvel.foundation.exceptions import ConfigurationError
from arvel.queue.job import Job
from arvel.scheduler.entry import ScheduleEntry


class _DummyJob(Job):
    async def handle(self) -> None:
        pass


class TestScheduleEntryFluentAPI:
    """FR-002: Fluent interval methods produce correct cron expressions."""

    def test_every_minute(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).every_minute()
        assert entry.expression == "* * * * *"

    def test_every_five_minutes(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).every_five_minutes()
        assert entry.expression == "*/5 * * * *"

    def test_every_fifteen_minutes(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).every_fifteen_minutes()
        assert entry.expression == "*/15 * * * *"

    def test_every_thirty_minutes(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).every_thirty_minutes()
        assert entry.expression == "*/30 * * * *"

    def test_hourly(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).hourly()
        assert entry.expression == "0 * * * *"

    def test_daily(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily()
        assert entry.expression == "0 0 * * *"

    def test_daily_at(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily_at("08:30")
        assert entry.expression == "30 8 * * *"

    def test_weekly(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).weekly()
        assert entry.expression == "0 0 * * 0"

    def test_monthly(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).monthly()
        assert entry.expression == "0 0 1 * *"

    def test_custom_cron(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).cron("0 8 * * 1-5")
        assert entry.expression == "0 8 * * 1-5"

    def test_fluent_returns_self(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob)
        result = entry.daily_at("09:00")
        assert result is entry


class TestScheduleEntryCronValidation:
    """FR-003: Invalid cron raises ConfigurationError at registration."""

    def test_invalid_cron_raises_at_registration(self) -> None:
        with pytest.raises(ConfigurationError):
            ScheduleEntry(job_class=_DummyJob).cron("bad expression")

    def test_invalid_field_count_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            ScheduleEntry(job_class=_DummyJob).cron("* * *")

    def test_valid_cron_does_not_raise(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).cron("*/15 * * * *")
        assert entry.expression == "*/15 * * * *"


class TestScheduleEntryIsDue:
    """FR-004: is_due evaluates correctly against given time."""

    def test_every_minute_is_always_due(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).every_minute()
        now = datetime(2026, 4, 6, 14, 23, 0, tzinfo=UTC)
        assert entry.is_due(now) is True

    def test_hourly_due_at_top_of_hour(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).hourly()
        top = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)
        assert entry.is_due(top) is True

    def test_hourly_not_due_at_half_hour(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).hourly()
        half = datetime(2026, 4, 6, 14, 30, 0, tzinfo=UTC)
        assert entry.is_due(half) is False

    def test_daily_at_due_at_correct_time(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily_at("08:00")
        correct = datetime(2026, 4, 6, 8, 0, 0, tzinfo=UTC)
        assert entry.is_due(correct) is True

    def test_daily_at_not_due_at_wrong_time(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily_at("08:00")
        wrong = datetime(2026, 4, 6, 9, 0, 0, tzinfo=UTC)
        assert entry.is_due(wrong) is False

    def test_weekday_cron_due_on_monday(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).cron("0 8 * * 1-5")
        monday_8am = datetime(2026, 4, 6, 8, 0, 0, tzinfo=UTC)
        assert entry.is_due(monday_8am) is True

    def test_weekday_cron_not_due_on_sunday(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).cron("0 8 * * 1-5")
        sunday_8am = datetime(2026, 4, 5, 8, 0, 0, tzinfo=UTC)
        assert entry.is_due(sunday_8am) is False


class TestScheduleEntryTimezone:
    """FR-011: Per-entry timezone offsets evaluation."""

    def test_timezone_converts_evaluation(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily_at("09:00").timezone("Europe/Paris")
        utc_7am = datetime(2026, 4, 6, 7, 0, 0, tzinfo=UTC)
        assert entry.is_due(utc_7am) is True

    def test_default_timezone_is_utc(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily_at("08:00")
        assert entry.tz_name == "UTC"

    def test_custom_timezone_stored(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily_at("08:00").timezone("US/Eastern")
        assert entry.tz_name == "US/Eastern"


class TestScheduleEntryConditions:
    """FR-010: when/skip callbacks control dispatch eligibility."""

    def test_when_true_allows(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().when(lambda: True)
        assert entry.should_run() is True

    def test_when_false_prevents(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().when(lambda: False)
        assert entry.should_run() is False

    def test_skip_true_prevents(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().skip(lambda: True)
        assert entry.should_run() is False

    def test_skip_false_allows(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().skip(lambda: False)
        assert entry.should_run() is True

    def test_no_conditions_allows(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily()
        assert entry.should_run() is True


class TestScheduleEntryOverlap:
    """FR-009: without_overlapping configuration."""

    def test_overlap_disabled_by_default(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily()
        assert entry.prevent_overlap is False

    def test_without_overlapping_enables(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().without_overlapping()
        assert entry.prevent_overlap is True

    def test_without_overlapping_default_ttl(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().without_overlapping()
        assert entry.overlap_expires_after == 1800

    def test_without_overlapping_custom_ttl(self) -> None:
        entry = ScheduleEntry(job_class=_DummyJob).daily().without_overlapping(expires_after=600)
        assert entry.overlap_expires_after == 600
