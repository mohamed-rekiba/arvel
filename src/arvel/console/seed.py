"""``db:seed`` — run the app's database seeder (Laravel ``db:seed``)."""

from __future__ import annotations

from typing import Any

import typer

seed_app = typer.Typer()


@seed_app.command()
def db_seed() -> None:
    """Run the application's root database seeder."""
    from arvel.console.kernel import run_app_command

    run_app_command(_db_seed)


async def _db_seed(app: Any) -> None:
    if not app.bound("seeder"):
        typer.echo("no seeder bound; register one as 'seeder' in your app")
        raise typer.Exit(1)
    await app.make("seeder").run()
    typer.echo("seeding complete")
