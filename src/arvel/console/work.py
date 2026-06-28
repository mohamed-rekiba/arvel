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
