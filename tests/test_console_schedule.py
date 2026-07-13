"""Console (doc 13) — schedule:run command runs due scheduled tasks.

Also covers the Phase-5 wiring: the `schedule` binding (queue provider), the `Schedule` facade, and
loading scheduled tasks from routes/console.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.kernel import set_application
from arvel.kernel.application import Application
from arvel.queue.provider import QueueServiceProvider

runner = CliRunner()


@pytest.fixture
def app() -> Iterator[Application]:
    application = Application()
    QueueServiceProvider(application).register()  # binds "schedule"
    set_application(application)
    yield application
    set_application(None)


def test_queue_provider_binds_schedule(app: Application) -> None:
    from arvel.queue.scheduler import Schedule as ScheduleEngine

    assert app.bound("schedule")
    assert isinstance(app.make("schedule"), ScheduleEngine)


def test_facade_registers_against_the_bound_schedule(app: Application) -> None:
    from arvel import Schedule

    Schedule.call(lambda: None).daily()  # facade forwards to app("schedule")
    assert len(app.make("schedule").due_events(datetime(2020, 1, 1, 0, 0))) == 1  # midnight = due


async def test_facade_run_due_executes_tasks(app: Application) -> None:
    from arvel import Schedule

    ran: list[str] = []
    Schedule.call(lambda: ran.append("tick")).every_minute()
    await app.make("schedule").run_due(datetime.now())
    assert ran == ["tick"]


def test_load_console_routes_registers_scheduled_tasks(app: Application, tmp_path: Path) -> None:
    from arvel.console.kernel import load_console_routes

    console = tmp_path / "console.py"
    console.write_text("from arvel import Schedule\nSchedule.call(lambda: None).every_minute()\n")
    app.routing["console"] = str(console)
    load_console_routes(app)
    assert len(app.make("schedule").due_events(datetime.now())) == 1


def test_load_console_routes_is_a_noop_without_a_console_entry(app: Application) -> None:
    from arvel.console.kernel import load_console_routes

    load_console_routes(app)  # no routing["console"] → clean no-op, no crash
    assert app.make("schedule").due_events(datetime.now()) == []


def test_schedule_run_executes_due_tasks() -> None:
    from arvel.kernel import Application, set_application
    from arvel.queue.scheduler import Schedule

    ran: list[str] = []
    schedule = Schedule()
    schedule.call(lambda: ran.append("tick")).every_minute()

    app = Application()
    app.instance("schedule", schedule)
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["schedule:run"])
        assert result.exit_code == 0
        assert ran == ["tick"]
        assert "ran 1 due task" in result.output
    finally:
        set_application(None)


def test_schedule_run_without_binding_errors() -> None:
    from arvel.kernel import Application, set_application

    set_application(Application())  # active app, but no 'schedule' bound → binding-missing branch
    try:
        result = runner.invoke(build_cli(), ["schedule:run"])
        assert result.exit_code == 1
        assert "no schedule bound" in result.output
    finally:
        set_application(None)


# --- 6.2b: schedule:work — a dev loop ticking schedule:run every minute ----------------------


async def test_tick_loop_runs_due_tasks_repeatedly_until_stopped() -> None:
    from arvel.console.schedule import tick_loop
    from arvel.queue.scheduler import Schedule

    ticks: list[str] = []
    schedule = Schedule()
    schedule.call(lambda: ticks.append("tick")).every_minute()

    stop = asyncio.Event()

    async def _stop_soon() -> None:
        await asyncio.sleep(0.05)
        stop.set()

    stopper = asyncio.create_task(_stop_soon())
    await asyncio.wait_for(tick_loop(schedule, interval=0.01, stop=stop), timeout=5)
    await stopper
    assert len(ticks) >= 2  # ticked more than once before stopping


async def test_tick_loop_stops_immediately_when_already_stopped() -> None:
    from arvel.console.schedule import tick_loop
    from arvel.queue.scheduler import Schedule

    ticks: list[str] = []
    schedule = Schedule()
    schedule.call(lambda: ticks.append("tick")).every_minute()

    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(tick_loop(schedule, interval=60.0, stop=stop), timeout=1)
    assert ticks == []  # never ticked — already stopped before the first iteration


def test_schedule_work_is_registered_as_a_cli_command_and_errors_without_a_binding() -> None:
    from arvel.kernel import Application, set_application

    set_application(Application())  # active app, but no 'schedule' bound
    try:
        result = runner.invoke(build_cli(), ["schedule:work"])
        assert result.exit_code == 1
        assert "no schedule bound" in result.output
    finally:
        set_application(None)
