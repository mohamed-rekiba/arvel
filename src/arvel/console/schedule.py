"""``schedule:run`` — run the scheduled tasks that are due now (Laravel ``schedule:run``).

A cron entry calls this once a minute; it resolves the app's ``schedule`` binding (a
``Schedule``) and runs the events due at the current minute. Grounded in knowledge/port/13.
"""

from __future__ import annotations

from typing import Any

import typer

schedule_app = typer.Typer()


async def _run_due(schedule: Any) -> int:
    from datetime import datetime

    now = datetime.now()
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
