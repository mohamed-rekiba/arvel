"""Queues (doc 12) — the task Schedule: cron matching + fluent cadence + run_due. Test-first."""

from __future__ import annotations

from datetime import datetime

import pytest

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


def test_cron_stepped_range_and_named_fields_do_not_crash() -> None:
    from arvel.queue.scheduler import cron_matches

    event = Schedule().call(_noop).cron("0-30/10 * * * *")
    assert event.is_due(datetime(2026, 1, 1, 9, 0))
    assert event.is_due(datetime(2026, 1, 1, 9, 10))
    assert event.is_due(datetime(2026, 1, 1, 9, 30))
    assert not event.is_due(datetime(2026, 1, 1, 9, 25))  # not on the /10 step
    assert not event.is_due(datetime(2026, 1, 1, 9, 40))  # past the range
    # named month + weekday range (2026-01-02 is a Friday)
    assert cron_matches("0 0 * jan mon-fri", datetime(2026, 1, 2, 0, 0))
    assert not cron_matches("0 0 * jan mon-fri", datetime(2026, 1, 3, 0, 0))  # Saturday


async def test_on_one_server_skips_a_sequential_second_run_in_the_same_minute() -> None:
    from arvel.cache import CacheManager

    cache = CacheManager().driver("array")
    ran: list[str] = []

    async def _tick() -> None:
        ran.append("ran")

    moment = datetime(2026, 1, 1, 9, 10)
    a = Schedule(cache=cache).call(_tick).every_minute().on_one_server().name("shared")
    b = Schedule(cache=cache).call(_tick).every_minute().on_one_server().name("shared")
    await a.run(moment)
    await b.run(moment)  # claim held for the minute → second run skips (no artificial overlap)
    assert ran == ["ran"]


async def test_run_due_executes_only_due_events() -> None:
    schedule = Schedule()
    ran: list[str] = []
    schedule.call(lambda: ran.append("minutely")).every_minute()
    schedule.call(lambda: ran.append("hourly")).hourly()

    await schedule.run_due(datetime(2026, 1, 1, 4, 30))  # not on the hour
    assert ran == ["minutely"]


async def test_a_throwing_event_does_not_kill_the_tick() -> None:
    """run_due keeps going past a failing task (logged, not raised) — one bad job must never
    starve every other schedule."""
    from datetime import datetime

    from arvel.queue.scheduler import Schedule

    schedule = Schedule()
    ran: list[str] = []

    async def boom() -> None:
        raise RuntimeError("scheduled boom")

    async def fine() -> None:
        ran.append("fine")

    schedule.call(boom).every_minute()
    schedule.call(fine).every_minute()
    await schedule.run_due(datetime(2026, 7, 2, 12, 0))
    assert ran == ["fine"]  # the second task still ran


# --- 18: frequency helpers -----------------------------------------------------------------


def test_weekly_is_due_only_sunday_midnight() -> None:
    event = Schedule().call(_noop).weekly()
    assert event.is_due(datetime(2026, 1, 4, 0, 0))  # a Sunday
    assert not event.is_due(datetime(2026, 1, 5, 0, 0))  # Monday
    assert not event.is_due(datetime(2026, 1, 4, 1, 0))


def test_monthly_is_due_only_on_the_1st() -> None:
    event = Schedule().call(_noop).monthly()
    assert event.is_due(datetime(2026, 3, 1, 0, 0))
    assert not event.is_due(datetime(2026, 3, 2, 0, 0))


def test_quarterly_is_due_on_the_1st_of_jan_apr_jul_oct() -> None:
    event = Schedule().call(_noop).quarterly()
    for month in (1, 4, 7, 10):
        assert event.is_due(datetime(2026, month, 1, 0, 0))
    assert not event.is_due(datetime(2026, 2, 1, 0, 0))


def test_yearly_is_due_only_jan_1st() -> None:
    event = Schedule().call(_noop).yearly()
    assert event.is_due(datetime(2026, 1, 1, 0, 0))
    assert not event.is_due(datetime(2027, 2, 1, 0, 0))


def test_twice_daily_is_due_at_both_hours() -> None:
    event = Schedule().call(_noop).twice_daily(1, 13)
    assert event.is_due(datetime(2026, 1, 1, 1, 0))
    assert event.is_due(datetime(2026, 1, 1, 13, 0))
    assert not event.is_due(datetime(2026, 1, 1, 7, 0))


def test_weekdays_excludes_the_weekend() -> None:
    event = Schedule().call(_noop).daily().weekdays()
    assert event.is_due(datetime(2026, 1, 5, 0, 0))  # Monday
    assert not event.is_due(datetime(2026, 1, 4, 0, 0))  # Sunday
    assert not event.is_due(datetime(2026, 1, 10, 0, 0))  # Saturday


def test_weekends_is_due_only_saturday_sunday() -> None:
    event = Schedule().call(_noop).daily().weekends()
    assert event.is_due(datetime(2026, 1, 4, 0, 0))  # Sunday
    assert event.is_due(datetime(2026, 1, 10, 0, 0))  # Saturday
    assert not event.is_due(datetime(2026, 1, 5, 0, 0))  # Monday


def test_between_gates_by_time_of_day() -> None:
    event = Schedule().call(_noop).every_minute().between("09:00", "17:00")
    assert event.is_due(datetime(2026, 1, 1, 12, 0))
    assert not event.is_due(datetime(2026, 1, 1, 8, 59))
    assert not event.is_due(datetime(2026, 1, 1, 17, 1))


def test_when_and_skip_gate_execution() -> None:
    event = Schedule().call(_noop).every_minute().when(lambda: False)
    assert not event.is_due(datetime(2026, 1, 1, 0, 0))

    event = Schedule().call(_noop).every_minute().skip(lambda: True)
    assert not event.is_due(datetime(2026, 1, 1, 0, 0))

    event = Schedule().call(_noop).every_minute().when(lambda: True).skip(lambda: False)
    assert event.is_due(datetime(2026, 1, 1, 0, 0))


def test_environments_gates_by_app_env() -> None:
    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set("app", {"env": "staging"})
    set_application(app)
    try:
        event = Schedule().call(_noop).every_minute().environments("production")
        assert not event.is_due(datetime(2026, 1, 1, 0, 0))

        event = Schedule().call(_noop).every_minute().environments("staging", "production")
        assert event.is_due(datetime(2026, 1, 1, 0, 0))
    finally:
        set_application(None)


def test_timezone_shifts_the_matched_moment() -> None:
    """`moment` is treated as UTC; `timezone('...')` re-matches the cron expression against it
    shifted into that zone."""
    event = Schedule().call(_noop).daily_at("09:00").timezone("America/New_York")
    # 09:00 America/New_York (UTC-5 in January) is 14:00 UTC.
    assert event.is_due(datetime(2026, 1, 1, 14, 0))
    assert not event.is_due(datetime(2026, 1, 1, 9, 0))


# --- 18: hooks -------------------------------------------------------------------------------


async def test_hooks_fire_in_order_on_success() -> None:
    calls: list[str] = []
    event = (
        Schedule()
        .call(lambda: calls.append("task"))
        .every_minute()
        .before(lambda: calls.append("before"))
        .after(lambda: calls.append("after"))
        .on_success(lambda: calls.append("on_success"))
        .on_failure(lambda: calls.append("on_failure"))
    )
    await event.run()
    assert calls == ["before", "task", "on_success", "after"]


async def test_on_failure_fires_instead_of_on_success_and_after_still_runs() -> None:
    calls: list[str] = []

    def boom() -> None:
        calls.append("task")
        raise RuntimeError("boom")

    event = (
        Schedule()
        .call(boom)
        .every_minute()
        .before(lambda: calls.append("before"))
        .after(lambda: calls.append("after"))
        .on_success(lambda: calls.append("on_success"))
        .on_failure(lambda: calls.append("on_failure"))
    )
    with pytest.raises(RuntimeError):
        await event.run()
    assert calls == ["before", "task", "on_failure", "after"]


# --- 18: A3 one_server + without_overlapping (real cache locks) --------------------------------


async def test_one_server_runs_on_exactly_one_of_two_schedulers() -> None:
    """Two separately-constructed `Schedule()`s sharing one cache backend, racing over the same
    `on_one_server()` event: exactly one of them actually runs it (A3 — no longer a no-op)."""
    import asyncio

    from arvel.cache import CacheManager

    cache = CacheManager().driver()
    ran: list[str] = []

    async def _tick() -> None:
        # A real suspension point so the loop actually interleaves the two `run()` tasks — the
        # array cache lock is otherwise fully synchronous (no `await` inside its body), so without
        # one, whichever task the loop picks first would run to completion (acquire→run→release)
        # before the other ever starts, and the lock would already be free again by then.
        await asyncio.sleep(0.02)
        ran.append("ran")

    scheduler_a = Schedule(cache=cache)
    scheduler_b = Schedule(cache=cache)
    event_a = scheduler_a.call(_tick).every_minute().on_one_server()
    event_b = scheduler_b.call(_tick).every_minute().on_one_server()

    await asyncio.gather(event_a.run(), event_b.run())
    assert ran == ["ran"]  # only one of the two actually ran it


async def test_without_overlapping_skips_a_tick_while_the_prior_run_is_in_flight() -> None:
    import asyncio

    from arvel.cache import CacheManager

    cache = CacheManager().driver()
    ran: list[str] = []

    async def _slow() -> None:
        ran.append("start")
        await asyncio.sleep(0.05)
        ran.append("end")

    event = Schedule(cache=cache).call(_slow).every_minute().without_overlapping(60)

    first = asyncio.create_task(event.run())
    await asyncio.sleep(0.01)  # let the first tick acquire the lock and start sleeping
    await event.run()  # a second tick while the first is still in flight -> skipped
    await first
    assert ran == ["start", "end"]  # never two concurrent starts


async def test_after_hook_does_not_fire_on_a_lost_one_server_tick() -> None:
    # review BLOCKING: after() must fire only when the event actually ran — not on the N-1
    # instances that lose the one_server race (else .on_one_server().after(report) fires everywhere)
    import asyncio

    from arvel.cache import CacheManager

    cache = CacheManager().driver()
    ran: list[str] = []
    after: list[str] = []

    async def _tick() -> None:
        await asyncio.sleep(0.02)
        ran.append("ran")

    a = (
        Schedule(cache=cache)
        .call(_tick)
        .every_minute()
        .on_one_server()
        .after(lambda: after.append("after"))
    )
    b = (
        Schedule(cache=cache)
        .call(_tick)
        .every_minute()
        .on_one_server()
        .after(lambda: after.append("after"))
    )
    await asyncio.gather(a.run(), b.run())
    assert ran == ["ran"]  # exactly one ran
    assert after == ["after"]  # ...and after fired exactly once, not on the lost tick
