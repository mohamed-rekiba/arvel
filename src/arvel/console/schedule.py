"""``schedule:run``/``schedule:work`` — run the scheduled tasks that are due now, or loop forever.

A cron entry calls ``schedule:run`` once a minute; it resolves the app's ``schedule`` binding (a
``Schedule``) and runs the events due at the current minute. ``schedule:work`` (6.2b) is the local
dev convenience for when there's no cron: it ticks the same ``run_due`` once a minute, forever,
until SIGINT/SIGTERM. Grounded in knowledge/port/13.
"""

from __future__ import annotations

from typing import Any

import typer

schedule_app = typer.Typer()
work_app = typer.Typer()


async def _run_due(schedule: Any, moment: Any = None) -> int:
    from datetime import datetime

    now = moment if moment is not None else datetime.now()
    due = schedule.due_events(now)
    await schedule.run_due(now)
    return len(due)


@schedule_app.command()
def schedule_run() -> None:
    """Run any scheduled tasks that are due."""
    from arvel.console.kernel import run_app_command

    run_app_command(_schedule_run)


async def _schedule_run(app: Any) -> None:
    if not app.bound("schedule"):
        typer.echo("no schedule bound; define one in your app")
        raise typer.Exit(1)
    count = await _run_due(app.make("schedule"))
    typer.echo(f"ran {count} due task(s)")


@work_app.command()
def schedule_work() -> None:
    """Tick the schedule once a minute, forever, until interrupted (SIGINT/SIGTERM) — the local
    dev stand-in for a real cron entry calling ``schedule:run``."""
    from arvel.console.kernel import run_app_command

    run_app_command(_schedule_work)


async def _schedule_work(app: Any) -> None:
    if not app.bound("schedule"):
        typer.echo("no schedule bound; define one in your app")
        raise typer.Exit(1)
    typer.echo("ticking the schedule every minute (Ctrl-C to stop)")
    await tick_loop(app.make("schedule"))


async def tick_loop(schedule: Any, *, interval: float = 60.0, stop: Any = None) -> None:
    """The ``schedule:work`` loop: run due tasks, wait, repeat — until ``stop`` is set. Reuses
    ``schedule_run``'s own internals (``_run_due``) for each tick, so a bad tick is logged and
    skipped exactly like ``schedule:run``'s, never killing the loop.

    ``interval``/``stop`` are test seams: a real run wires ``stop`` to SIGINT/SIGTERM and uses the
    default 60s interval; a test injects a short interval and/or its own ``stop`` event to end the
    loop deterministically instead of waiting on a real signal.
    """
    import asyncio
    import contextlib
    import signal

    finish = stop if stop is not None else asyncio.Event()
    loop = asyncio.get_running_loop()
    handled_signals: list[signal.Signals] = []
    for sig_num in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig_num, finish.set)
            handled_signals.append(sig_num)
    try:
        while not finish.is_set():
            await _run_due(schedule)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(finish.wait(), timeout=interval)
    finally:
        for sig_num in handled_signals:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(sig_num)
