"""Scheduler commands — run, work (daemon), and list entries."""

from __future__ import annotations

import asyncio
import importlib.util
import json as json_lib
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from arvel.scheduler.scheduler import Scheduler

schedule_app = typer.Typer(name="schedule", help="Task scheduler management commands.")


def _load_scheduler(app_dir: str) -> Scheduler:
    """Build a Scheduler, loading registrations from app/schedule.py when present."""
    from arvel.queue.config import QueueSettings
    from arvel.queue.manager import QueueManager
    from arvel.scheduler.config import SchedulerSettings
    from arvel.scheduler.locks import InMemoryLockBackend, NullLockBackend
    from arvel.scheduler.scheduler import Scheduler

    queue_settings = QueueSettings()
    manager = QueueManager()
    queue = manager.create_driver(queue_settings)

    scheduler_settings = SchedulerSettings()
    lock_backend = (
        InMemoryLockBackend() if scheduler_settings.lock_backend == "memory" else NullLockBackend()
    )

    scheduler = Scheduler(queue=queue, lock_backend=lock_backend)

    schedule_file = Path(app_dir) / "app" / "schedule.py"
    if schedule_file.exists():
        spec = importlib.util.spec_from_file_location("app.schedule", str(schedule_file))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["app.schedule"] = module
            spec.loader.exec_module(module)
            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(scheduler)

    return scheduler


@schedule_app.command("run")
def run(
    app_dir: str = typer.Option(".", "--app-dir", help="Application root directory."),
) -> None:
    """Dispatch due jobs once and exit."""
    scheduler = _load_scheduler(app_dir)
    count = asyncio.run(scheduler.run())
    typer.echo(f"Scheduler run complete: {count} job(s) dispatched.")


@schedule_app.command("work")
def work(
    app_dir: str = typer.Option(".", "--app-dir", help="Application root directory."),
    interval: int = typer.Option(60, "--interval", help="Tick interval in seconds."),
) -> None:
    """Run the scheduler as a long-lived daemon."""
    scheduler = _load_scheduler(app_dir)
    shutdown = False

    def _handle_signal(_sig: int, _frame: object) -> None:
        nonlocal shutdown
        shutdown = True
        typer.echo("\nShutdown signal received. Stopping scheduler...")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    typer.echo(f"Scheduler daemon started (interval: {interval}s). Press Ctrl+C to stop.")

    while not shutdown:
        count = asyncio.run(scheduler.run())
        now = datetime.now(UTC).strftime("%H:%M:%S")
        typer.echo(f"[{now}] Tick: {count} job(s) dispatched.")
        if not shutdown:
            try:
                asyncio.get_event_loop().run_until_complete(asyncio.sleep(interval))
            except KeyboardInterrupt:
                break

    typer.echo("Scheduler daemon stopped.")


@schedule_app.command("list")
def list_entries(
    app_dir: str = typer.Option(".", "--app-dir", help="Application root directory."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all registered schedule entries."""
    scheduler = _load_scheduler(app_dir)
    entries = scheduler.entries()

    rows = []
    for entry in entries:
        next_due = _next_due(entry.expression, entry.tz_name)
        rows.append(
            {
                "job": f"{entry.job_class.__name__}",
                "cron": entry.expression,
                "next_due": next_due,
                "timezone": entry.tz_name,
                "overlap_prevention": "Yes" if entry.prevent_overlap else "No",
            }
        )

    if json:
        typer.echo(json_lib.dumps(rows, indent=2))
        return

    if not rows:
        typer.echo("No scheduled entries registered.")
        return

    typer.echo(f"{'Job':<30} {'Cron':<20} {'Next Due':<22} {'TZ':<10} {'Overlap'}")
    typer.echo("-" * 92)
    for row in rows:
        typer.echo(
            f"{row['job']:<30} {row['cron']:<20} {row['next_due']:<22} "
            f"{row['timezone']:<10} {row['overlap_prevention']}"
        )


def _next_due(expression: str, tz_name: str) -> str:
    from zoneinfo import ZoneInfo

    from croniter import croniter

    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    cron = croniter(expression, now)
    next_dt = cron.get_next(datetime)
    return next_dt.strftime("%Y-%m-%d %H:%M:%S")
