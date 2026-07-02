"""``queue:work`` — process queued jobs (Laravel ``queue:work``)."""

from __future__ import annotations

from typing import Any

import typer

work_app = typer.Typer()


@work_app.command()
def queue_work(
    queue: str = typer.Option("default", "--queue", help="Comma-separated queue names."),
) -> None:
    """Run a worker that processes queued jobs until interrupted (Ctrl-C)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        if not app.bound("queue"):
            typer.echo("no queue bound; configure a queue in your app")
            raise typer.Exit(1)
        typer.echo(f"[queue:work] processing queues: {queue}")
        await app.make("queue").work(queue.split(","))

    run_app_command(_handler)


failed_app = typer.Typer()


@failed_app.command()
def queue_failed() -> None:
    """List the failed jobs (Laravel ``queue:failed``)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        # reached through the container-bound queue manager — console imports no queue internals (G2)
        jobs = await app.make("queue").failed_jobs()
        if not jobs:
            typer.echo("no failed jobs")
            return
        for job in jobs:
            typer.echo(f"{job.id}  {job.queue}  {job.failed_at}  {job.exception.splitlines()[0]}")

    run_app_command(_handler)


retry_app = typer.Typer()


@retry_app.command()
def queue_retry(
    id: str = typer.Argument(..., help="A failed-job id, or 'all' to retry every failed job."),
) -> None:
    """Re-dispatch a failed job and delete its record (Laravel ``queue:retry``)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        retried = await app.make("queue").retry_failed(None if id == "all" else id)
        if not retried:
            typer.echo(f"no failed job matches '{id}'")
            raise typer.Exit(1)
        for job in retried:
            typer.echo(f"retried {job.id}")

    run_app_command(_handler)
