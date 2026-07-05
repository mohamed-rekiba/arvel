"""``db:seed`` — run the app's database seeder."""

from __future__ import annotations

from typing import Any

import typer

seed_app = typer.Typer()


@seed_app.command()
def db_seed() -> None:
    """Run the application's root database seeder."""
    from arvel.console.kernel import run_app_command

    run_app_command(run_seed)


async def run_seed(app: Any) -> None:
    from arvel.console import ConsoleOutput
    from arvel.database.seeder import reset_called_once

    if not app.bound("seeder"):
        typer.echo("no seeder bound; register one as 'seeder' in your app")
        raise typer.Exit(1)
    reset_called_once()  # scope call_once dedup to this run
    seeder = app.make("seeder")
    seeder.output = ConsoleOutput()  # give the seeder a live console: progress bars + section lines
    await seeder.run()
    typer.echo("seeding complete")
