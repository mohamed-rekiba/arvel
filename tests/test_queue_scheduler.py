"""Queues (doc 12) — the task Schedule: cron matching + fluent cadence + run_due. Test-first."""

from __future__ import annotations

from datetime import datetime

from arvel.queue.scheduler import Schedule


def _noop() -> None: ...


def test_daily_at_is_due_only_at_that_minute() -> None:
    event = Schedule().call(_noop).daily_at("02:30")
    assert event.is_due(datetime(2026, 1, 1, 2, 30))
    assert not event.is_due(datetime(2026, 1, 1, 2, 31))
    assert not event.is_due(datetime(2026, 1, 1, 3, 30))


def test_hourly_is_due_on_the_hour() -> None:
    event = Schedule().call(_noop).hourly()
    assert event.is_due(datetime(2026, 1, 1, 5, 0))
    assert not event.is_due(datetime(2026, 1, 1, 5, 30))


def test_cron_step_expression() -> None:
    event = Schedule().call(_noop).cron("*/5 * * * *")
    assert event.is_due(datetime(2026, 1, 1, 9, 10))
    assert not event.is_due(datetime(2026, 1, 1, 9, 11))


def test_on_one_server_flag() -> None:
    event = Schedule().call(_noop).on_one_server()
    assert event.one_server is True


async def test_run_due_executes_only_due_events() -> None:
    schedule = Schedule()
    ran: list[str] = []
    schedule.call(lambda: ran.append("minutely")).every_minute()
    schedule.call(lambda: ran.append("hourly")).hourly()

    await schedule.run_due(datetime(2026, 1, 1, 4, 30))  # not on the hour
    assert ran == ["minutely"]
