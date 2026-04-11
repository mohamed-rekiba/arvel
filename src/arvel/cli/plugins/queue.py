"""Queue commands — workers, restarts, and failed job management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin
    from arvel.queue.config import QueueSettings

_app = typer.Typer(name="queue", help="Queue worker management commands.")

RESTART_SIGNAL_PATH = Path("/tmp/arvel-queue-restart")  # noqa: S108


def _get_settings() -> QueueSettings:
    from arvel.queue.config import QueueSettings

    return QueueSettings()


@_app.command()
def work(
    queue: str = typer.Option("", "--queue", help="Queue name to process."),
) -> None:
    """Start a background queue worker."""
    settings = _get_settings()
    queue_name = queue if queue else settings.default
    driver = settings.driver

    if driver == "sync":
        typer.echo("Warning: The 'sync' driver is not supported for background workers.")
        typer.echo("Sync driver executes jobs inline. Use 'taskiq' for a real worker.")
        return

    if driver == "null":
        typer.echo("Warning: The 'null' driver is not supported for background workers.")
        typer.echo("Null driver discards all jobs. Use 'taskiq' for a real worker.")
        return

    if driver == "taskiq":
        _start_taskiq_worker(settings, queue_name)
    else:
        typer.echo(f"Error: Unknown queue driver '{driver}'.")
        raise typer.Exit(code=1)


def _start_taskiq_worker(settings: QueueSettings, queue_name: str) -> None:
    try:
        import taskiq  # noqa: F401
    except ImportError:
        typer.echo("Error: Taskiq is not installed. Install with: pip install arvel[taskiq]")
        raise typer.Exit(code=1) from None

    effective_url = settings.taskiq_url if settings.taskiq_url else settings.redis_url
    typer.echo(
        f"Starting Taskiq worker on queue '{queue_name}' "
        f"(broker: {settings.taskiq_broker}, url: {effective_url})"
    )


@_app.command()
def restart() -> None:
    """Tell running workers to restart gracefully."""
    RESTART_SIGNAL_PATH.write_text("restart")
    typer.echo(f"Restart signal written to {RESTART_SIGNAL_PATH}")


@_app.command()
def failed() -> None:
    """List all failed jobs."""
    typer.echo("ID  | Queue    | Job Class                     | Failed At           | Exception")
    typer.echo("-" * 90)
    typer.echo("(No database session configured for CLI — use programmatic API)")


@_app.command()
def retry(
    job_id: int = typer.Argument(..., help="ID of the failed job to retry."),
) -> None:
    """Retry a specific failed job."""
    typer.echo(f"Retrying failed job {job_id}...")
    typer.echo("(No database session configured for CLI — use programmatic API)")


@_app.command(name="retry-all")
def retry_all() -> None:
    """Retry every failed job."""
    typer.echo("Retrying all failed jobs...")
    typer.echo("(No database session configured for CLI — use programmatic API)")


@_app.command()
def forget(
    job_id: int = typer.Argument(..., help="ID of the failed job to delete."),
) -> None:
    """Delete a specific failed job permanently."""
    typer.echo(f"Forgetting failed job {job_id}...")
    typer.echo("(No database session configured for CLI — use programmatic API)")


@_app.command()
def flush() -> None:
    """Purge all failed jobs."""
    typer.echo("Flushing all failed jobs...")
    typer.echo("(No database session configured for CLI — use programmatic API)")


class _Plugin:
    name = "queue"
    help = "Queue worker management commands."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
