"""Tests for the Schedule DSL — FR-015-001..006."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from arvel.scheduling import Schedule


@pytest.fixture
def schedule() -> Schedule:
    """Fresh Schedule instance for each test."""
    from arvel.scheduling import Schedule

    return Schedule()


class TestScheduleCall:
    """FR-015-001 — schedule.call(callable)."""

    def test_call_registers_a_task(self, schedule: Schedule) -> None:
        async def my_task() -> None: ...

        schedule.call(my_task).daily()

        tasks = schedule.tasks()
        assert len(tasks) == 1
        assert tasks[0].expression == "0 0 * * *"

    def test_call_derives_name_from_callable(self, schedule: Schedule) -> None:
        async def my_named_task() -> None: ...

        schedule.call(my_named_task).hourly()

        assert "my_named_task" in schedule.tasks()[0].name

    def test_explicit_name_overrides_derivation(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).hourly().name("custom-name")

        assert schedule.tasks()[0].name == "custom-name"


class TestScheduleCommand:
    """FR-015-001 — schedule.command(name)."""

    def test_command_registers_a_task(self, schedule: Schedule) -> None:
        schedule.command("cache:clear").dailyAt("02:00")

        tasks = schedule.tasks()
        assert len(tasks) == 1
        assert tasks[0].expression == "0 2 * * *"
        assert "cache:clear" in tasks[0].name


class TestFrequencyModifiers:
    """FR-015-002 — frequency modifiers."""

    @pytest.mark.parametrize(
        ("modifier", "expected_cron"),
        [
            ("everyMinute", "* * * * *"),
            ("everyFiveMinutes", "*/5 * * * *"),
            ("everyTenMinutes", "*/10 * * * *"),
            ("everyFifteenMinutes", "*/15 * * * *"),
            ("everyThirtyMinutes", "*/30 * * * *"),
            ("hourly", "0 * * * *"),
            ("daily", "0 0 * * *"),
            ("monthly", "0 0 1 * *"),
            ("yearly", "0 0 1 1 *"),
        ],
    )
    def test_frequency_modifier_produces_correct_cron(
        self, schedule: Schedule, modifier: str, expected_cron: str
    ) -> None:
        async def t() -> None: ...

        getattr(schedule.call(t), modifier)()

        assert schedule.tasks()[0].expression == expected_cron

    def test_daily_at_produces_correct_cron(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).dailyAt("14:30")

        assert schedule.tasks()[0].expression == "30 14 * * *"

    def test_weekly_on_produces_correct_cron(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).weeklyOn(0, "08:00")  # Sunday 08:00

        assert schedule.tasks()[0].expression == "0 8 * * 0"

    def test_monthly_on_produces_correct_cron(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).monthlyOn(15, "12:00")  # 15th of month, noon

        assert schedule.tasks()[0].expression == "0 12 15 * *"

    def test_arbitrary_cron(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).cron("*/7 3,15 * * 1-5")

        assert schedule.tasks()[0].expression == "*/7 3,15 * * 1-5"

    def test_invalid_cron_raises_at_registration(self, schedule: Schedule) -> None:
        from arvel.scheduling.exceptions import ScheduleError

        async def t() -> None: ...

        with pytest.raises(ScheduleError):
            schedule.call(t).cron("not a cron")


class TestTimezoneOverride:
    """FR-015-006 — .timezone() override."""

    def test_timezone_defaults_to_utc(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).daily()

        assert schedule.tasks()[0].timezone == "UTC"

    def test_timezone_can_be_overridden(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).daily().timezone("Europe/Paris")

        assert schedule.tasks()[0].timezone == "Europe/Paris"


class TestModifierBooleans:
    """FR-015-007, FR-015-008 — withoutOverlapping, onOneServer flags."""

    def test_without_overlapping_defaults_false(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).daily()

        assert schedule.tasks()[0].without_overlapping is False

    def test_without_overlapping_sets_true(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).daily().withoutOverlapping()

        assert schedule.tasks()[0].without_overlapping is True

    def test_on_one_server_defaults_false(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).daily()

        assert schedule.tasks()[0].on_one_server is False

    def test_on_one_server_sets_true(self, schedule: Schedule) -> None:
        async def t() -> None: ...

        schedule.call(t).daily().onOneServer()

        assert schedule.tasks()[0].on_one_server is True
