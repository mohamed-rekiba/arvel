"""``db:seed`` — run the app's database seeder."""

from __future__ import annotations

from typing import Any

import typer

seed_app = typer.Typer()


@seed_app.command()
def db_seed(
    force: bool = typer.Option(
        False, "--force", help="Skip the confirmation prompt / allow in production."
    ),
) -> None:
    """Run the application's root database seeder."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        from arvel.console.guard import confirm_destructive

        confirm_destructive(app, force=force, action="run the database seeders")
        await run_seed(app)

    run_app_command(_handler)


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
