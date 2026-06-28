"""``migrate`` / ``migrate:rollback`` — apply or revert migrations (Laravel ``migrate``).

Resolves the app's bound ``migrator`` (an Alembic-backed Migrator) and its ``migrations``
list and drives them. The command imports nothing from ``arvel.database`` so the console stays
light (startup NFR / G2) — the heavy bits are resolved from the container at runtime.
Grounded in knowledge/port/08.
"""

from __future__ import annotations

from typing import Any, cast

import typer

migrate_app = typer.Typer()


def _resolve(app: Any) -> tuple[Any, list[Any]]:
    if not app.bound("migrator"):
        typer.echo("no migrator bound; configure a database in your app")
        raise typer.Exit(1)
    migrations = cast("list[Any]", app.make("migrations") if app.bound("migrations") else [])
    return app.make("migrator"), migrations


@migrate_app.command()
def migrate() -> None:
    """Apply all outstanding migrations."""
    from arvel.console.kernel import run_app_command

    run_app_command(_migrate)


async def _migrate(app: Any) -> None:
    migrator, migrations = _resolve(app)
    await migrator.run(migrations)
    typer.echo(f"migrated {len(migrations)} migration(s)")


rollback_app = typer.Typer()


@rollback_app.command()
def migrate_rollback() -> None:
    """Roll back the bound migrations (reverse order)."""
    from arvel.console.kernel import run_app_command

    run_app_command(_rollback)


async def _rollback(app: Any) -> None:
    migrator, migrations = _resolve(app)
    await migrator.rollback(migrations)
    typer.echo(f"rolled back {len(migrations)} migration(s)")
