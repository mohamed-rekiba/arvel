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
    applied = await migrator.run(migrations)
    typer.echo(f"migrated {applied} migration(s)" if applied else "Nothing to migrate.")


rollback_app = typer.Typer()


@rollback_app.command()
def migrate_rollback() -> None:
    """Roll back the bound migrations (reverse order)."""
    from arvel.console.kernel import run_app_command

    run_app_command(_rollback)


async def _rollback(app: Any) -> None:
    migrator, migrations = _resolve(app)
    reverted = await migrator.rollback(migrations)
    typer.echo(f"rolled back {reverted} migration(s)" if reverted else "Nothing to roll back.")


fresh_app = typer.Typer()


@fresh_app.command()
def migrate_fresh() -> None:
    """Drop all tables, then re-run every migration (Laravel `migrate:fresh`)."""
    from arvel.console.kernel import run_app_command

    run_app_command(_fresh)


async def _fresh(app: Any) -> None:
    migrator, migrations = _resolve(app)
    dropped = await migrator.drop_all()
    await migrator.run(migrations)
    typer.echo(f"dropped {dropped} table(s); migrated {len(migrations)} migration(s)")


refresh_app = typer.Typer()


@refresh_app.command()
def migrate_refresh(
    seed: bool = typer.Option(False, "--seed", help="Run the app's seeder after refreshing."),
) -> None:
    """Roll back all migrations, then re-run them (Laravel `migrate:refresh`)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        await _refresh(app, seed=seed)

    run_app_command(_handler)


async def _refresh(app: Any, *, seed: bool) -> None:
    migrator, migrations = _resolve(app)
    await migrator.rollback(migrations)
    await migrator.run(migrations)
    typer.echo(f"refreshed {len(migrations)} migration(s)")
    if seed:
        if not app.bound("seeder"):
            typer.echo("no seeder bound; register one as 'seeder' in your app")
            raise typer.Exit(1)
        await app.make("seeder").run()
        typer.echo("seeding complete")


wipe_app = typer.Typer()


@wipe_app.command()
def db_wipe() -> None:
    """Drop all tables without re-migrating (Laravel `db:wipe`)."""
    from arvel.console.kernel import run_app_command

    run_app_command(_wipe)


async def _wipe(app: Any) -> None:
    migrator, _ = _resolve(app)
    dropped = await migrator.drop_all()
    typer.echo(f"dropped {dropped} table(s)")
